from pyftpdlib.authorizers import DummyAuthorizer
from pyftpdlib.handlers import FTPHandler
from pyftpdlib.servers import FTPServer
import os
from uuid_gen import get_current_uuid
from tcp_server_final import FTP_FOLDER
# Folder where uploaded files will be stored
#FTP_FOLDER = "D:/PrinterImages/temp"

os.makedirs(FTP_FOLDER, exist_ok=True)

# Username and Password
USERNAME = "oakter"
PASSWORD = "oakter"

authorizer = DummyAuthorizer()

# Full permissions
authorizer.add_user(
    USERNAME,
    PASSWORD,
    FTP_FOLDER,
    perm="elradfmwMT"
)



class MyFTPHandler(FTPHandler):

    def on_file_received(self, file):
        try:
            folder = os.path.dirname(file)
            ext = os.path.splitext(file)[1]

            # New filename
            _uuid = get_current_uuid()
            new_name = f"{_uuid}{ext}"
            new_path = os.path.join(folder, new_name)

            os.rename(file, new_path)

            print(f"Renamed:")
            print(f"{file}")
            print("↓")
            print(f"{new_path}")

        except Exception as e:
            print("Rename Error:", e)

handler = MyFTPHandler
handler.authorizer = authorizer
handler.banner = "Python FTP Server Ready"


def start_ftp_server():
    server = FTPServer(("0.0.0.0", 21), handler)

    print("FTP Server Running...")
    print("Host : 0.0.0.0")
    print("Port : 21")
    print(f"Folder : {FTP_FOLDER}")

    server.serve_forever()