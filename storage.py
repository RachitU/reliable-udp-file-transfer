files = {}


def init_file(file_id, total_chunks):
    files[file_id] = {
        "total": total_chunks,
        "chunks": {}
    }


def store_chunk(file_id, seq, data):
    if file_id not in files:
        return

    files[file_id]["chunks"][seq] = data


def is_complete(file_id):
    info = files[file_id]
    return len(info["chunks"]) == info["total"]


def reconstruct_file(file_id):

    info = files[file_id]

    filename = f"received_{file_id}"

    with open(filename, "wb") as f:
        for i in range(info["total"]):
            f.write(info["chunks"][i].encode())

    print(f"File reconstructed: {filename}")