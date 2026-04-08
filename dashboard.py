from flask import Flask, render_template, request, jsonify
from flask_cors import CORS
import json, os, threading, socket, time, base64, hashlib
from datetime import datetime
from cryptography.fernet import Fernet
app   = Flask(__name__)
CORS(app)
FERNET_KEY = b'Cf7VSMEymKRdJSWPMuA_RcAblHtMkmq-T1NpyrepZNs='
# ── Config ────────────────────────────────────────────────────────────────────
CHUNK_SIZE   = 1024
WINDOW_SIZE  = 4
FTP_SERVER   = "10.20.201.117"
FTP_PORT     = 9000
UDP_TIMEOUT  = 2      # seconds
MAX_RETRIES  = 8
fernet = Fernet(FERNET_KEY)

# ── In-memory state ───────────────────────────────────────────────────────────
server_status = {"online": False}
transfers     = {}        # file_id → transfer dict
transfers_lock = threading.Lock()


# ─── helpers ──────────────────────────────────────────────────────────────────

def sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def now_iso() -> str:
    return datetime.now().isoformat()


def make_udp_sock():
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    s.settimeout(UDP_TIMEOUT)
    return s


def send_recv(sock, pkt_bytes, expect_type, retries=5):
    for _ in range(retries):
        sock.sendto(pkt_bytes, (FTP_SERVER, FTP_PORT))
        try:
            raw, _ = sock.recvfrom(65535)
            msg    = json.loads(raw.decode())
            if msg["type"] == expect_type:
                return msg
        except socket.timeout:
            pass
    raise TimeoutError(f"No {expect_type} after {retries} tries")


def emit_event(file_id, kind, **kw):
    """Append a real-time event to the transfer's event queue."""
    with transfers_lock:
        t = transfers.get(file_id)
        if t:
            t["events"].append({"kind": kind, "ts": now_iso(), **kw})


# ─── Real UDP transfer thread ─────────────────────────────────────────────────

def run_transfer(file_id, filename, raw_bytes):
    """Performs the actual sliding-window UDP transfer and writes events."""

    chunks          = [raw_bytes[i:i+CHUNK_SIZE]
                       for i in range(0, len(raw_bytes), CHUNK_SIZE)]
    total_chunks    = len(chunks)
    chunk_checksums = [sha256_hex(c) for c in chunks]
    file_hash       = sha256_hex(raw_bytes)

    with transfers_lock:
        transfers[file_id].update({
            "total_chunks":   total_chunks,
            "file_hash":      file_hash,
            "chunk_states":   ["unsent"] * total_chunks,
            "received_chunks": [],
            "stat_sent":      0,
            "stat_acked":     0,
            "stat_lost":      0,
            "stat_retx":      0,
            "integrity_ok":   None,   # None = pending
            "status":         "running",
        })

    sock = make_udp_sock()

    try:
        # ── INIT ──────────────────────────────────────────────────────────
        emit_event(file_id, "flow", direction="to-server",
                   label=f"INIT ({total_chunks} chunks)")
        init_pkt = json.dumps({
            "type": "INIT", "file_id": file_id,
            "total": total_chunks, "file_hash": file_hash,
        }).encode()
        send_recv(sock, init_pkt, "ACK")
        emit_event(file_id, "log", level="success",
                   msg=f"INIT ACK received  file_hash={file_hash[:12]}…")
        emit_event(file_id, "flow", direction="to-client", label="ACK(-1)")
        time.sleep(0.2)

        # ── RESUME ────────────────────────────────────────────────────────
        emit_event(file_id, "flow", direction="to-server", label="RESUME_REQ")
        resume_pkt = json.dumps({"type": "RESUME_REQ",
                                 "file_id": file_id}).encode()
        resp = send_recv(sock, resume_pkt, "RESUME_RESP")
        already_received = set(resp["received"])
        emit_event(file_id, "log", level="info",
                   msg=f"Server has {len(already_received)} chunks already")
        emit_event(file_id, "flow", direction="to-client",
                   label=f"RESUME_RESP({len(already_received)})")

        with transfers_lock:
            t = transfers[file_id]
            for s in already_received:
                if 0 <= s < total_chunks:
                    t["chunk_states"][s] = "acked"
                    t["stat_acked"] += 1

        # ── Sliding Window DATA ────────────────────────────────────────────
        base = 0

        while base < total_chunks:
            window_end = min(base + WINDOW_SIZE, total_chunks)
            to_send    = [s for s in range(base, window_end)
                          if s not in already_received]

            # Mark window-active
            with transfers_lock:
                t = transfers[file_id]
                for s in range(base, window_end):
                    if t["chunk_states"][s] == "unsent":
                        t["chunk_states"][s] = "sending"
                t["window_base"] = base
                t["window_end"]  = window_end - 1

            emit_event(file_id, "window",
                       base=base, end=window_end-1, sending=to_send)
            
            # Send all in window
            for seq in to_send:
                encrypted = fernet.encrypt(chunks[seq])
                checksum  = sha256_hex(chunks[seq])

                pkt = json.dumps({
    "type": "DATA",
    "file_id": file_id,
    "seq": seq,
    "total": total_chunks,
    "data": base64.b64encode(encrypted).decode(),
    "checksum": checksum,   # ✅ matches what you're sending
}).encode() 
                sock.sendto(pkt, (FTP_SERVER, FTP_PORT))
                with transfers_lock:
                    transfers[file_id]["stat_sent"] += 1
                emit_event(file_id, "flow", direction="to-server",
                           label=f"DATA({seq})")
                emit_event(file_id, "chunk", seq=seq, state="sending")

            # Collect ACKs
            acked  = set()
            nacked = set()
            deadline = time.time() + UDP_TIMEOUT * 2

            while len(acked) + len(nacked) < len(to_send) and time.time() < deadline:
                try:
                    raw, _ = sock.recvfrom(65535)
                    msg    = json.loads(raw.decode())
                    if msg["type"] == "ACK":
                        seq = msg["seq"]
                        if seq in to_send:
                            acked.add(seq)
                            already_received.add(seq)
                            with transfers_lock:
                                t = transfers[file_id]
                                t["chunk_states"][seq] = "acked"
                                t["stat_acked"] += 1
                            emit_event(file_id, "flow", direction="to-client",
                                       label=f"ACK({seq})")
                            emit_event(file_id, "chunk", seq=seq, state="acked")
                    elif msg["type"] == "NACK":
                        seq = msg["seq"]
                        if seq in to_send:
                            nacked.add(seq)
                            with transfers_lock:
                                transfers[file_id]["chunk_states"][seq] = "lost"
                            emit_event(file_id, "chunk", seq=seq, state="lost")
                            emit_event(file_id, "log", level="error",
                                       msg=f"NACK chunk {seq}: {msg.get('reason')}")
                except socket.timeout:
                    break

            # Mark timeouts as lost
            missing = (set(to_send) - acked) | nacked
            for seq in missing:
                if seq not in nacked:  # timed-out (not explicit NACK)
                    with transfers_lock:
                        transfers[file_id]["chunk_states"][seq] = "lost"
                        transfers[file_id]["stat_lost"] += 1
                    emit_event(file_id, "chunk", seq=seq, state="lost")
                    emit_event(file_id, "log", level="warn",
                               msg=f"Timeout – chunk {seq} presumed lost")
                    emit_event(file_id, "flow", direction="lost",
                               label=f"✗ DROP({seq})")

            # Retransmit loop
            retries = 0
            while missing and retries < MAX_RETRIES:
                retries += 1
                for seq in sorted(missing):
                    encrypted = fernet.encrypt(chunks[seq])   # ✅ encrypt again
                    checksum  = sha256_hex(chunks[seq])      # ✅ checksum of encrypted

                    pkt = json.dumps({
        "type": "DATA",
        "file_id": file_id,
        "seq": seq,
        "total": total_chunks,
        "data": base64.b64encode(encrypted).decode(),
        "checksum": checksum,
    }).encode()

                    sock.sendto(pkt, (FTP_SERVER, FTP_PORT))

                    with transfers_lock:
                        transfers[file_id]["stat_retx"] += 1
                        transfers[file_id]["chunk_states"][seq] = "retransmit"

                    emit_event(file_id, "chunk", seq=seq, state="retransmit")
                    emit_event(file_id, "flow", direction="to-server",
               label=f"DATA({seq}) [RETX]")
                    emit_event(file_id, "log", level="warn",
               msg=f"Retransmitting chunk {seq}")

                newly_acked = set()
                deadline2   = time.time() + UDP_TIMEOUT
                while time.time() < deadline2:
                    try:
                        raw, _ = sock.recvfrom(65535)
                        msg    = json.loads(raw.decode())
                        if msg["type"] == "ACK" and msg["seq"] in missing:
                            seq = msg["seq"]
                            newly_acked.add(seq)
                            already_received.add(seq)
                            with transfers_lock:
                                t = transfers[file_id]
                                t["chunk_states"][seq] = "acked"
                                t["stat_acked"] += 1
                            emit_event(file_id, "flow", direction="to-client",
                                       label=f"ACK({seq})")
                            emit_event(file_id, "chunk", seq=seq, state="acked")
                        elif msg["type"] == "NACK":
                            seq = msg.get("seq", None)
                            if seq is not None and seq in missing:
                                emit_event(file_id, "log", level="error",
                                msg=f"NACK({seq}) integrity fail on retransmit")
                    except socket.timeout:
                        break
                missing -= newly_acked

            if missing:
                emit_event(file_id, "log", level="error",
                           msg=f"Gave up on chunks {sorted(missing)}")
            else:
                base = window_end

        # ── FIN ───────────────────────────────────────────────────────────
        fin_pkt = json.dumps({
            "type": "FIN", "file_id": file_id, "file_hash": file_hash,
        }).encode()
        emit_event(file_id, "flow", direction="to-server",
                   label="FIN")

        try:
            fin_ack = send_recv(sock, fin_pkt, "FIN_ACK")
            result  = fin_ack.get("result", "?")
            integrity_ok = (result == "ok")
            emit_event(file_id, "flow", direction="to-client",
                       label=f"FIN_ACK ({result})")
            if integrity_ok:
                emit_event(file_id, "log", level="success",
                           msg=f"✅ Server confirmed file integrity  "
                               f"SHA-256={file_hash[:16]}…")
            else:
                emit_event(file_id, "log", level="error",
                           msg=f"❌ Server reported integrity failure: {result}")
        except TimeoutError:
            integrity_ok = False
            emit_event(file_id, "log", level="warn",
                       msg="FIN_ACK not received (server may be down)")

        with transfers_lock:
            transfers[file_id]["status"]       = "completed"
            transfers[file_id]["integrity_ok"] = integrity_ok
            transfers[file_id]["end_time"]     = now_iso()

        emit_event(file_id, "complete",
                   integrity_ok=integrity_ok, file_hash=file_hash)

    except Exception as e:
        emit_event(file_id, "log", level="error", msg=f"Transfer error: {e}")
        with transfers_lock:
            transfers[file_id]["status"] = "error"
    finally:
        sock.close()


# ─── Background server health-check ──────────────────────────────────────────

def bg_server_check():
    while True:
        try:
            s = make_udp_sock()
            s.settimeout(1)
            s.sendto(json.dumps({"type": "PING"}).encode(),
                     (FTP_SERVER, FTP_PORT))
            raw, _ = s.recvfrom(1024)
            msg    = json.loads(raw.decode())
            server_status["online"] = (msg.get("type") == "PONG")
            s.close()
        except Exception:
            server_status["online"] = False
        time.sleep(5)


# ─── Flask routes ─────────────────────────────────────────────────────────────

@app.route("/")
def index():
    return render_template("dashboard.html")


@app.route("/api/status")
def get_status():
    return jsonify({
        "server_status": "online" if server_status["online"] else "offline",
        "timestamp":     now_iso(),
    })


@app.route("/api/server/check")
def check_server():
    return jsonify({"status": "online" if server_status["online"] else "offline"})


@app.route("/api/upload", methods=["POST"])
def upload_file():
    if "file" not in request.files:
        return jsonify({"error": "No file provided"}), 400
    f = request.files["file"]
    if f.filename == "":
        return jsonify({"error": "No file selected"}), 400

    try:
        raw_bytes = f.read()
        file_id   = f"client_{int(time.time()*1000)}_{f.filename}"
        file_hash = sha256_hex(raw_bytes)
        total_chunks = (len(raw_bytes) + CHUNK_SIZE - 1) // CHUNK_SIZE

        os.makedirs("uploads", exist_ok=True)
        save_path = os.path.join("uploads", f.filename)
        with open(save_path, "wb") as fh:
            fh.write(raw_bytes)

        with transfers_lock:
            transfers[file_id] = {
                "file_id":        file_id,
                "filename":       f.filename,
                "size":           len(raw_bytes),
                "file_hash":      file_hash,
                "total_chunks":   total_chunks,
                "chunk_states":   ["unsent"] * total_chunks,
                "stat_sent":      0,
                "stat_acked":     0,
                "stat_lost":      0,
                "stat_retx":      0,
                "status":         "starting",
                "integrity_ok":   None,
                "start_time":     now_iso(),
                "events":         [],
                "window_base":    0,
                "window_end":     min(WINDOW_SIZE - 1, total_chunks - 1),
            }

        threading.Thread(target=run_transfer,
                         args=(file_id, f.filename, raw_bytes),
                         daemon=True).start()

        return jsonify({
            "success":     True,
            "file_id":     file_id,
            "filename":    f.filename,
            "size":        len(raw_bytes),
            "chunks":      total_chunks,
            "file_hash":   file_hash,
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/transfer/<path:file_id>/state")
def transfer_state(file_id):
    """Full snapshot – chunk states, stats, events since `since` index."""
    since = int(request.args.get("since", 0))
    with transfers_lock:
        t = transfers.get(file_id)
        if not t:
            return jsonify({"error": "not found"}), 404
        snap = {
            "file_id":       t["file_id"],
            "filename":      t["filename"],
            "size":          t["size"],
            "file_hash":     t["file_hash"],
            "total_chunks":  t["total_chunks"],
            "chunk_states":  list(t["chunk_states"]),
            "stat_sent":     t["stat_sent"],
            "stat_acked":    t["stat_acked"],
            "stat_lost":     t["stat_lost"],
            "stat_retx":     t["stat_retx"],
            "status":        t["status"],
            "integrity_ok":  t["integrity_ok"],
            "window_base":   t.get("window_base", 0),
            "window_end":    t.get("window_end", 0),
            "events":        t["events"][since:],
            "event_count":   len(t["events"]),
            "progress":      (t["stat_acked"] / t["total_chunks"] * 100)
                             if t["total_chunks"] else 0,
        }
    return jsonify(snap)


@app.route("/api/transfers")
def get_transfers():
    with transfers_lock:
        active    = [_summary(t) for t in transfers.values()
                     if t["status"] in ("running", "starting")]
        completed = [_summary(t) for t in transfers.values()
                     if t["status"] in ("completed", "error")]
    return jsonify({"active": active, "completed": completed})


def _summary(t):
    return {
        "file_id":      t["file_id"],
        "filename":     t["filename"],
        "total_chunks": t["total_chunks"],
        "stat_acked":   t["stat_acked"],
        "stat_lost":    t["stat_lost"],
        "stat_retx":    t["stat_retx"],
        "status":       t["status"],
        "integrity_ok": t["integrity_ok"],
        "progress":     (t["stat_acked"] / t["total_chunks"] * 100)
                        if t["total_chunks"] else 0,
    }


@app.route("/api/files")
def list_files():
    os.makedirs("uploads", exist_ok=True)
    files_list = []
    for fname in os.listdir("uploads"):
        fp = os.path.join("uploads", fname)
        if os.path.isfile(fp):
            files_list.append({
                "name":     fname,
                "size":     os.path.getsize(fp),
                "modified": datetime.fromtimestamp(
                                os.path.getmtime(fp)).isoformat(),
            })
    return jsonify(files_list)


@app.route("/api/stats")
def get_stats():
    with transfers_lock:
        active    = sum(1 for t in transfers.values()
                        if t["status"] in ("running", "starting"))
        completed = sum(1 for t in transfers.values()
                        if t["status"] == "completed")
        total_bytes = sum(t["size"] for t in transfers.values())
    return jsonify({
        "active_transfers":     active,
        "completed_transfers":  completed,
        "total_bytes":          total_bytes,
        "server_status":        "online" if server_status["online"] else "offline",
    })


if __name__ == "__main__":
    threading.Thread(target=bg_server_check, daemon=True).start()
    print("Dashboard → http://localhost:5000")
    app.run(host="0.0.0.0", port=5000, debug=False)
