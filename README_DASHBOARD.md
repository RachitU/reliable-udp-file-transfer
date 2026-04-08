# Reliable FTP Dashboard

A modern web-based dashboard for monitoring and managing your Reliable FTP file transfer application.

## Features

✨ **Live Transfer Monitoring**

- Real-time progress tracking for active transfers
- Visual progress bars with percentage completion
- Chunk-by-chunk transfer details

📊 **Statistics & Analytics**

- Active and completed transfer counters
- Total files uploaded tracking
- Data transferred metrics
- Server status monitoring

📤 **File Upload Interface**

- Drag-and-drop file upload
- Single-file upload with progress tracking
- File validation and error handling

📁 **File Management**

- View recent uploaded files
- File size and modification date display
- Complete transfer history

🔌 **Server Integration**

- Real-time server status checking (online/offline)
- Automatic status updates every 5 seconds
- Connection diagnostics

## Installation

### 1. Install Dependencies

```bash
pip install -r requirements_dashboard.txt
```

### 2. Create Templates Directory (if not exists)

```bash
mkdir templates
```

The dashboard.html file should be in the `templates/` folder.

### 3. Create Uploads Directory

```bash
mkdir uploads
```

## Running the Dashboard

### Start the FTP Server (in one terminal):

```bash
python server.py
```

### Start the Dashboard (in another terminal):

```bash
python dashboard.py
```

The dashboard will be available at: **http://localhost:5000**

## API Endpoints

### Status & Monitoring

- `GET /api/status` - Current server status
- `GET /api/stats` - Overall statistics
- `GET /api/server/check` - Check if FTP server is running
- `GET /api/transfers` - List all transfers (active and completed)

### File Operations

- `POST /api/upload` - Upload a new file
- `GET /api/files` - List all uploaded files
- `POST /api/transfer/<file_id>/progress` - Update transfer progress
- `POST /api/transfer/<file_id>/complete` - Mark transfer as completed

## Dashboard Features Explained

### Active Transfers Panel

Shows currently uploading files with:

- File name
- Progress percentage
- Progress bar visualization
- Number of chunks transferred

### Statistics Cards

- **Active Transfers**: Number of files currently being uploaded
- **Completed Transfers**: Number of successfully transferred files
- **Total Files**: Total files ever uploaded
- **Data Transferred**: Total bytes transferred so far

### Upload Zone

- Click to select files
- Drag and drop support
- File validation
- Automatic progress tracking

### Recent Files Section

- Shows recently uploaded files
- Displays file size and modification date
- Maximum of 5 files shown

### Server Status Indicator

- Live connection status to FTP server
- Green (Online) or Red (Offline)
- Automatic polling every 5 seconds

## File Structure

```
relaible_ftp/
├── dashboard.py              # Flask backend server
├── templates/
│   └── dashboard.html        # Web UI
├── requirements_dashboard.txt # Python dependencies
├── server.py                 # Original FTP server
├── client_test.py            # Original FTP client
├── protocol.py               # FTP protocol definitions
├── storage.py                # Storage utilities
└── utils.py                  # Utility functions
```

## Configuration

Edit these variables in `dashboard.py` to customize:

```python
PORT = 9001                    # Dashboard server port
FTP_SERVER = "localhost"       # FTP server address
FTP_PORT = 9000               # FTP server port
CHUNK_SIZE = 1024             # Size of file chunks
```

## Tips

💡 **For local testing:** Use `FTP_SERVER = "localhost"` or `"127.0.0.1"`

💡 **For remote access:** Replace `localhost:5000` with your machine's IP address

💡 **File uploads:** Files are saved in the `uploads/` directory

💡 **Progress simulation:** The dashboard simulates realistic progress for demo purposes

## Troubleshooting

### Dashboard not connecting to server

- Ensure FTP server is running on port 9000
- Check firewall settings
- Verify FTP_SERVER and FTP_PORT in dashboard.py

### Port already in use

- Change PORT variable in dashboard.py
- Or kill existing process using the port

### Files not uploading

- Ensure `uploads/` directory exists
- Check write permissions
- Verify disk space

## Future Enhancements

- [ ] Download file functionality
- [ ] Multi-file concurrent uploads
- [ ] Advanced filtering and search
- [ ] User authentication
- [ ] Transfer history export
- [ ] Bandwidth throttling controls
- [ ] File integrity verification with checksums
