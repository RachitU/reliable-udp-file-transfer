import socket
import json
import base64
import time
import hashlib
FERNET_KEY = b'Cf7VSMEymKRdJSWPMuA_RcAblHtMkmq-T1NpyrepZNs='
CHUNK_SIZE   = 1024
WINDOW_SIZE  = 4
SERVER_IP    = "127.0.0.1"
SERVER_PORT  = 9000
TIMEOUT      = 2          # seconds per recv attempt
MAX_RETRIES  = 8          # per chunk before giving up

sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
sock.settimeout(TIMEOUT)
from cryptography.fernet import Fernet

fernet = Fernet(FERNET_KEY)

# ─── helpers ──────────────────────────────────────────────────────────────────

def sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def send_recv(packet_bytes, expect_type, retries=5):
    """Send a packet and wait for a specific response type. Returns parsed JSON."""
    for attempt in range(retries):
        sock.sendto(packet_bytes, (SERVER_IP, SERVER_PORT))
        try:
            raw, _ = sock.recvfrom(65535)
            msg = json.loads(raw.decode())
            if msg["type"] == expect_type:
                return msg
        except socket.timeout:
            print(f"  Timeout waiting for {expect_type} (attempt {attempt+1}/{retries})")
    raise TimeoutError(f"No {expect_type} after {retries} attempts")


def split_file(filename):
    chunks = []
    with open(filename, "rb") as f:
        while True:
            data = f.read(CHUNK_SIZE)
            if not data:
                break
            chunks.append(data)
    return chunks


# ─── main ─────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    filename = "test.txt"

    # Read file & compute whole-file hash before we start
    with open(filename, "rb") as fh:
        raw_file = fh.read()
    file_hash = sha256_hex(raw_file)
    chunks = [raw_file[i:i+CHUNK_SIZE] for i in range(0, len(raw_file), CHUNK_SIZE)]
    total_chunks = len(chunks)

    # Pre-compute per-chunk checksums
    chunk_checksums = [sha256_hex(c) for c in chunks]

    print(f"File : {filename}")
    print(f"Size : {len(raw_file)} bytes")
    print(f"Hash : {file_hash}")
    print(f"Chunks: {total_chunks}")

    file_id = f"client_{int(time.time())}"
    print(f"file_id: {file_id}\n")

    # ── INIT ──────────────────────────────────────────────────────────────────
    init_packet = json.dumps({
        "type":      "INIT",
        "file_id":   file_id,
        "total":     total_chunks,
        "file_hash": file_hash,
    }).encode()

    print("→ INIT")
    send_recv(init_packet, "ACK")
    print("← ACK(-1)  INIT confirmed")
    time.sleep(0.3)

    # ── RESUME ────────────────────────────────────────────────────────────────
    resume_pkt = json.dumps({"type": "RESUME_REQ", "file_id": file_id}).encode()
    print("\n→ RESUME_REQ")
    resp = send_recv(resume_pkt, "RESUME_RESP")
    received_chunks = set(resp["received"])
    print(f"← RESUME_RESP  server has: {sorted(received_chunks)}")

    # ── DATA (sliding window) ─────────────────────────────────────────────────
    base = 0

    while base < total_chunks:
        window_end = min(base + WINDOW_SIZE, total_chunks)
        to_send    = [s for s in range(base, window_end)
                      if s not in received_chunks]

        print(f"\nWindow [{base}–{window_end-1}]  sending={to_send}")

        # Send all chunks in the current window
        for seq in to_send:
            encrypted = fernet.encrypt(chunks[seq])

            chunk = chunks[seq]
            pkt   = json.dumps({
                "type":     "DATA",
                "file_id":  file_id,
                "seq":      seq,
                "total":    total_chunks,
                "data":     base64.b64encode(encrypted).decode(),
                "checksum": chunk_checksums[seq],   # ← integrity field
            }).encode()
            print(f"  → DATA({seq})  sha256={chunk_checksums[seq][:12]}…")
            sock.sendto(pkt, (SERVER_IP, SERVER_PORT))

        # Collect ACKs / NACKs
        acked  = set()
        nacked = set()
        deadline = time.time() + TIMEOUT * 2

        while len(acked) + len(nacked) < len(to_send) and time.time() < deadline:
            try:
                raw, _ = sock.recvfrom(65535)
                msg    = json.loads(raw.decode())
                if msg["type"] == "ACK":
                    seq = msg["seq"]
                    if seq in to_send:
                        acked.add(seq)
                        received_chunks.add(seq)
                        print(f"  ← ACK({seq})")
                elif msg["type"] == "NACK":
                    seq = msg["seq"]
                    print(f"  ← NACK({seq})  reason={msg.get('reason')}")
                    nacked.add(seq)
            except socket.timeout:
                break

        # Retransmit missing + NACKed chunks
        missing = (set(to_send) - acked) | nacked
        retries = 0

        while missing and retries < MAX_RETRIES:
            retries += 1
            print(f"  Retransmitting {sorted(missing)}  (attempt {retries})")
            for seq in sorted(missing):
                chunk = chunks[seq]
                pkt   = json.dumps({
                    "type":     "DATA",
                    "file_id":  file_id,
                    "seq":      seq,
                    "total":    total_chunks,
                    "data":     base64.b64encode(chunk).decode(),
                    "checksum": chunk_checksums[seq],
                }).encode()
                sock.sendto(pkt, (SERVER_IP, SERVER_PORT))

            newly_acked = set()
            deadline2   = time.time() + TIMEOUT
            while time.time() < deadline2:
                try:
                    raw, _ = sock.recvfrom(65535)
                    msg    = json.loads(raw.decode())
                    if msg["type"] == "ACK" and msg["seq"] in missing:
                        newly_acked.add(msg["seq"])
                        received_chunks.add(msg["seq"])
                        print(f"    ← ACK({msg['seq']})  (retransmit)")
                    elif msg["type"] == "NACK" and msg["seq"] in missing:
                        print(f"    ← NACK({msg['seq']})  still bad – will retry")
                except socket.timeout:
                    break

            missing -= newly_acked

        if missing:
            print(f"  [WARN] Gave up on chunks {sorted(missing)} after {MAX_RETRIES} retries")
        else:
            base = window_end

    # ── FIN ───────────────────────────────────────────────────────────────────
    fin_pkt = json.dumps({
        "type":      "FIN",
        "file_id":   file_id,
        "file_hash": file_hash,
    }).encode()

    print("\n→ FIN")
    try:
        fin_ack = send_recv(fin_pkt, "FIN_ACK", retries=5)
        result  = fin_ack.get("result", "?")
        if result == "ok":
            print(f"← FIN_ACK  ✅ Integrity confirmed by server  ({file_hash[:16]}…)")
        elif result == "integrity_fail":
            print(f"← FIN_ACK  ❌ Server reports file hash mismatch!")
        else:
            print(f"← FIN_ACK  result={result}")
    except TimeoutError:
        print("FIN_ACK not received – server may have dropped FIN")

    print("\n✅ Transfer complete")
