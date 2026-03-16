# Reliable File Transfer over UDP

## Overview
This project implements a reliable file transfer protocol on top of UDP. Since UDP does not guarantee reliable delivery, ordering, or retransmission of packets, this system introduces reliability mechanisms at the application layer.

The implementation includes:
- File chunking
- Sequence numbers
- Sliding window protocol
- Acknowledgements (ACKs)
- Retransmission of lost packets
- Resume support for interrupted transfers

The system consists of a client that sends files and a server that receives and reconstructs them.

---

## Features

### Reliable Data Transfer
Ensures all file chunks are delivered correctly even when packets are lost.

### Sliding Window Protocol
Multiple packets can be sent before waiting for acknowledgements, improving transmission efficiency.

### Packet Loss Simulation
The server intentionally drops packets once to demonstrate retransmission and reliability mechanisms.

### Resume Interrupted Transfers
If a transfer is interrupted, the client can resume by sending only the missing chunks.

### File Reconstruction
The server reconstructs the file after receiving all chunks.

---

## Project Structure

```
project-folder/
│
├── client.py           # Client program that sends files
├── server.py           # Server program that receives files
├── test.txt            # Example file to transfer
└── received_test.txt   # Reconstructed file on server
```

---

## How It Works

### 1. File Chunking
The client reads the file and splits it into fixed-size chunks.

```
CHUNK_SIZE = 1024 bytes
```

Each chunk is assigned a sequence number to ensure proper ordering.

---

### 2. Initialization
The client sends an INIT packet to notify the server that a file transfer will begin.

Example packet:

```
{
  "type": "INIT",
  "file_id": "file1",
  "total": 50
}
```

The server acknowledges this request before the transfer begins.

---

### 3. Resume Support
Before sending data, the client checks which chunks already exist on the server.

```
Client → RESUME_REQ
Server → RESUME_RESP
```

The server responds with the list of received chunks so the client sends only missing ones.

---

### 4. Sliding Window Transmission
The client sends chunks using a sliding window protocol.

```
WINDOW_SIZE = 4
```

Example:

```
Send chunks 0 1 2 3
Wait for acknowledgements
Slide window
Send chunks 4 5 6 7
```

This improves efficiency compared to sending one packet at a time.

---

### 5. Packet Loss Simulation
The server simulates network unreliability by dropping the first instance of each chunk.

Example:

```
DATA(seq=5) → dropped
Client retransmits seq=5
DATA(seq=5) → stored
```

This demonstrates retransmission behavior.

---

### 6. Acknowledgements
For each received chunk, the server sends an acknowledgement:

```
ACK seq = 5
```

The client uses these ACKs to determine which packets were successfully received.

---

### 7. Retransmission
If acknowledgements are not received within a timeout period, the client retransmits missing packets.

Example:

```
Missing chunks: {5}
Retransmitting chunk 5
```

---

### 8. File Reconstruction
After receiving all chunks, the server reconstructs the file by combining them in sequence order.

```
chunk0 + chunk1 + chunk2 + ... + chunkN
```

The final output is saved as:

```
received_test.txt
```

---

## Technologies Used
- Python
- UDP sockets
- JSON packet structure
- Base64 encoding

---

## How to Run

### 1. Start the Server

```
python server.py
```

### 2. Run the Client

```
python client.py
```

The client will send `test.txt` to the server and the server will reconstruct it as `received_test.txt`.

---

## Concepts Demonstrated
- Reliable data transfer over unreliable protocols
- Sliding window protocol
- Packet retransmission
- Sequence numbering
- Resume file transfer
- Application-layer protocol design

---

## Authors
Computer Networks Project – Reliable File Transfer over UDP
