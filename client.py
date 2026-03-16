import socket
import json
import base64

CHUNK_SIZE = 1024
WINDOW_SIZE = 4
SERVER_IP = "127.0.0.1"
SERVER_PORT = 9000

sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
sock.settimeout(2)


def split_file(filename):
    chunks = []

    with open(filename, "rb") as f:
        while True:
            data = f.read(CHUNK_SIZE)

            if not data:
                break

            chunks.append(data)

    return chunks


if __name__ == "__main__":

    filename = "test.txt"

    chunks = split_file(filename)
    total_chunks = len(chunks)

    print("Total chunks:", total_chunks)

    file_id = "file1"

    # ---------------- INIT ----------------
    init_packet = {
        "type": "INIT",
        "file_id": file_id,
        "total": total_chunks
    }

    sock.sendto(json.dumps(init_packet).encode(), (SERVER_IP, SERVER_PORT))

    while True:
        try:
            data, _ = sock.recvfrom(65535)
            msg = json.loads(data.decode())

            if msg["type"] == "ACK" and msg["seq"] == -1:
                print("INIT ACK received")
                break

        except socket.timeout:
            print("Retrying INIT...")
            sock.sendto(json.dumps(init_packet).encode(), (SERVER_IP, SERVER_PORT))

    # ---------------- RESUME ----------------
    resume_packet = {
        "type": "RESUME_REQ",
        "file_id": file_id
    }

    sock.sendto(json.dumps(resume_packet).encode(), (SERVER_IP, SERVER_PORT))

    while True:
        data, _ = sock.recvfrom(65535)
        resp = json.loads(data.decode())

        if resp["type"] == "RESUME_RESP":
            received_chunks = set(resp["received"])
            break

    print("Server already has:", received_chunks)

    base = 0

    while base < total_chunks:

        window_end = min(base + WINDOW_SIZE, total_chunks)

        print("\nSending window:", base, "to", window_end - 1)

        sent_chunks = set()
        acked_chunks = set()

        for seq in range(base, window_end):

            if seq in received_chunks:
                continue

            chunk = chunks[seq]

            packet = {
                "type": "DATA",
                "file_id": file_id,
                "seq": seq,
                "total": total_chunks,
                "data": base64.b64encode(chunk).decode()
            }

            print("Sending chunk", seq)

            sock.sendto(json.dumps(packet).encode(), (SERVER_IP, SERVER_PORT))

            sent_chunks.add(seq)

        try:
            while len(acked_chunks) < len(sent_chunks):

                ack_data, _ = sock.recvfrom(65535)

                ack = json.loads(ack_data.decode())

                if ack["type"] == "ACK":

                    seq = ack["seq"]

                    print("ACK received for", seq)

                    acked_chunks.add(seq)

        except socket.timeout:
            pass

        missing = sent_chunks - acked_chunks

        if missing:

            print("Missing chunks:", missing)

            for seq in missing:

                chunk = chunks[seq]

                packet = {
                    "type": "DATA",
                    "file_id": file_id,
                    "seq": seq,
                    "total": total_chunks,
                    "data": base64.b64encode(chunk).decode()
                }

                print("Retransmitting chunk", seq)

                sock.sendto(json.dumps(packet).encode(), (SERVER_IP, SERVER_PORT))

        else:
            base = window_end

    # ---------------- FIN ----------------
    fin_packet = {
        "type": "FIN",
        "file_id": file_id
    }

    sock.sendto(json.dumps(fin_packet).encode(), (SERVER_IP, SERVER_PORT))

    print("\nTransfer complete")