import json
import hashlib


def chunk_checksum(data: bytes) -> str:
    """SHA-256 checksum of raw chunk bytes."""
    return hashlib.sha256(data).hexdigest()


def file_checksum(data: bytes) -> str:
    """SHA-256 checksum of the full file bytes."""
    return hashlib.sha256(data).hexdigest()


def create_packet(packet_type, file_id="", seq=0, total=0, data="",
                  checksum="", file_hash=""):
    packet = {
        "type": packet_type,
        "file_id": file_id,
        "seq": seq,
        "total": total,
        "data": data,
        "checksum": checksum,    # per-chunk SHA-256 (hex)
        "file_hash": file_hash,  # whole-file SHA-256, sent in INIT + FIN
    }
    return json.dumps(packet).encode()


def parse_packet(packet_bytes):
    packet = json.loads(packet_bytes.decode())
    return (
        packet["type"],
        packet.get("file_id"),
        packet.get("seq"),
        packet.get("total"),
        packet.get("data"),
        packet.get("checksum", ""),
        packet.get("file_hash", ""),
    )
