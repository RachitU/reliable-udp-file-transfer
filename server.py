import socket
import json
import base64
import hashlib

SERVER_IP = "0.0.0.0"
PORT = 9000
BUFFER_SIZE = 65535
FERNET_KEY = b'Cf7VSMEymKRdJSWPMuA_RcAblHtMkmq-T1NpyrepZNs='
# Simulate one-time packet loss per chunk (teaching demo)
lost_once = {}
from cryptography.fernet import Fernet

fernet = Fernet(FERNET_KEY)
sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
sock.bind((SERVER_IP, PORT))

print(f"Server listening on port {PORT}")

files = {}


def sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


while True:
    try:
        data, addr = sock.recvfrom(BUFFER_SIZE)
        packet = json.loads(data.decode())

        packet_type = packet["type"]
        file_id = packet.get("file_id", "")

        print(f"Packet {packet_type} from {addr}")

        # ── PING (dashboard health-check) ──────────────────────────────────
        if packet_type == "PING":
            sock.sendto(json.dumps({"type": "PONG"}).encode(), addr)

        # ── INIT ──────────────────────────────────────────────────────────
        elif packet_type == "INIT":
            total     = packet["total"]
            file_hash = packet.get("file_hash", "")   # expected whole-file hash

            if file_id not in files:
                files[file_id] = {
                    "total":     total,
                    "chunks":    {},
                    "checksums": {},               # seq -> expected chunk checksum
                    "file_hash": file_hash,        # whole-file SHA-256
                    "bad_chunks": [],
                }

            print(f"Initialized transfer {file_id}  chunks={total}  "
                  f"file_hash={file_hash[:16]}…")

            ack = {"type": "ACK", "seq": -1}
            sock.sendto(json.dumps(ack).encode(), addr)

        # ── DATA ──────────────────────────────────────────────────────────
        elif packet_type == "DATA":
            if file_id not in files:
                print("Unknown file_id – ignored")
                continue

            seq           = packet["seq"]
            recv_checksum = packet.get("checksum", "")

            # ---- simulated one-time loss (demo only) ----------------------
            if file_id not in lost_once:
                lost_once[file_id] = set()
            if seq not in lost_once[file_id]:
                print(f"[LOSS SIM] dropping chunk {seq} once (file {file_id})")
                lost_once[file_id].add(seq)
                continue  # drop – client will retransmit
            # ---------------------------------------------------------------

            encrypted = base64.b64decode(packet["data"])

# 🔐 DECRYPT FIRST
            try:
                chunk_bytes = fernet.decrypt(encrypted)
            except Exception:
                print(f"[DECRYPT FAIL] chunk {seq}")
                nack = {
        "type": "NACK",
        "seq": seq,
        "reason": "decrypt_fail"
    }
                sock.sendto(json.dumps(nack).encode(), addr)
                continue

            # ── Integrity check: verify chunk checksum ──────────────────
            computed = hashlib.sha256(chunk_bytes).hexdigest()
            if recv_checksum and computed != recv_checksum:
                print(f"[INTEGRITY FAIL] chunk {seq}: "
                      f"expected {recv_checksum[:12]}… got {computed[:12]}…")
                nack = {"type": "NACK", "seq": seq,
                        "reason": "checksum_mismatch"}
                sock.sendto(json.dumps(nack).encode(), addr)
                files[file_id]["bad_chunks"].append(seq)
                continue

            files[file_id]["chunks"][seq]    = chunk_bytes
            files[file_id]["checksums"][seq] = computed
            print(f"Stored chunk {seq}  sha256={computed[:12]}…")

            ack = {"type": "ACK", "seq": seq}
            sock.sendto(json.dumps(ack).encode(), addr)

            # ── All chunks received → reconstruct ──────────────────────
            rec  = files[file_id]
            if len(rec["chunks"]) >= rec["total"]:
                print("All chunks received. Reconstructing file…")

                output = b"".join(rec["chunks"][i]
                                  for i in range(rec["total"]))

                # ── Whole-file integrity check ─────────────────────────
                actual_hash = hashlib.sha256(output).hexdigest()
                expected    = rec["file_hash"]
                integrity_ok = (expected == "" or actual_hash == expected)

                if integrity_ok:
                    outfile = f"received_{file_id}.txt"
                    with open(outfile, "wb") as f:
                        f.write(output)
                    print(f"File reconstructed → {outfile}")
                    print(f"[INTEGRITY OK] SHA-256 {actual_hash[:16]}…")
                else:
                    print(f"[INTEGRITY FAIL] file hash mismatch!")
                    print(f"  expected: {expected[:32]}…")
                    print(f"  actual:   {actual_hash[:32]}…")

        # ── RESUME ────────────────────────────────────────────────────────
        elif packet_type == "RESUME_REQ":
            if file_id in files:
                received = list(files[file_id]["chunks"].keys())
            else:
                received = []

            response = {"type": "RESUME_RESP", "received": received}
            sock.sendto(json.dumps(response).encode(), addr)
            print("Sent resume info:", received)

        # ── FIN ───────────────────────────────────────────────────────────
        elif packet_type == "FIN":
            client_file_hash = packet.get("file_hash", "")
            result = "ok"

            if file_id in files:
                rec = files[file_id]
                if len(rec["chunks"]) == rec["total"]:
                    output      = b"".join(rec["chunks"][i]
                                           for i in range(rec["total"]))
                    actual_hash = hashlib.sha256(output).hexdigest()
                    if client_file_hash and actual_hash != client_file_hash:
                        result = "integrity_fail"
                        print("[INTEGRITY FAIL] FIN hash mismatch")
                    else:
                        print(f"[INTEGRITY OK] FIN confirmed  {actual_hash[:16]}…")
                else:
                    result = "incomplete"
            else:
                result = "unknown"

            fin_ack = {"type": "FIN_ACK", "result": result,
                       "file_hash": client_file_hash}
            sock.sendto(json.dumps(fin_ack).encode(), addr)
            print(f"Transfer finished  result={result}")

    except Exception as e:
        print("Server error:", e)
