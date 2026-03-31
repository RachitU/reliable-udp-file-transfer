import socket
import json
import base64
import hashlib
SERVER_IP = "0.0.0.0"
PORT = 9000
BUFFER_SIZE = 65535

lost_once = {}

sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
sock.bind((SERVER_IP, PORT))

print(f"Server listening on port {PORT}")

files = {}

while True:
    try:

        data, addr = sock.recvfrom(BUFFER_SIZE)

        packet = json.loads(data.decode())

        packet_type = packet["type"]
        file_id = packet.get("file_id")

        print(f"Packet {packet_type} from {addr}")

        # ---------------- INIT ----------------
        if packet_type == "INIT":

            total = packet["total"]

            if file_id not in files:
                files[file_id] = {
                    "total": total,
                    "chunks": {}
                }

            print(f"Initialized file transfer {file_id} with {total} chunks")

            ack = {
                "type": "ACK",
                "seq": -1
            }

            sock.sendto(json.dumps(ack).encode(), addr)

        # ---------------- DATA ----------------
        elif packet_type == "DATA":

            if file_id not in files:
                print("Unknown file id")
                continue

            seq = packet["seq"]

            # simulate one-time packet loss
            if file_id not in lost_once:
                    lost_once[file_id] = set()

            if seq not in lost_once[file_id]:
                 print(f"Simulating packet loss for chunk {seq} (file {file_id})")
                 lost_once[file_id].add(seq)
                 continue

            chunk_data = base64.b64decode(packet["data"])

            files[file_id]["chunks"][seq] = chunk_data

            print("Stored chunk", seq)

            ack = {
                "type": "ACK",
                "seq": seq
            }

            sock.sendto(json.dumps(ack).encode(), addr)

            if len(files[file_id]["chunks"]) >= files[file_id]["total"]:

                print("All chunks received. Reconstructing file...")

                output = b""

                for i in range(files[file_id]["total"]):
                    output += files[file_id]["chunks"][i]

                with open(f"received_{file_id}.txt", "wb") as f:
                    f.write(output)

                print("File reconstructed!")

        # ---------------- RESUME ----------------
        elif packet_type == "RESUME_REQ":

            if file_id in files:
                received = list(files[file_id]["chunks"].keys())
            else:
                received = []

            response = {
                "type": "RESUME_RESP",
                "received": received
            }

            sock.sendto(json.dumps(response).encode(), addr)

            print("Sent resume info:", received)

        # ---------------- FIN ----------------
        elif packet_type == "FIN":

            print("Transfer finished")

    except Exception as e:
        print("Server error:", e)
