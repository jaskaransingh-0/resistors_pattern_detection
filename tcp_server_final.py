import socket
import threading
import logging
import re
from datetime import datetime
import pyodbc
from uuid_gen import generate_uuid
import json
from pathlib import Path

CONFIG_FILE = Path(__file__).resolve().parent / "config.json"

with open(CONFIG_FILE, "r", encoding="utf-8") as f:
    config = json.load(f)

DB_SERVER = config["database"]["server"]
FTP_FOLDER = config["ftp"]["folder"]

HOST = "0.0.0.0"
PORT = 9000

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S"
)
logger = logging.getLogger("TCP_SERVER")

conn = pyodbc.connect(
    "DRIVER={ODBC Driver 17 for SQL Server};"
    "SERVER= {DB_SERVER};"
    "DATABASE=test;"
    "Trusted_Connection=yes;"
)
cursor = conn.cursor()

#COMPANY_QR_PATTERN = re.compile(r".*_MIN/\d{2}-\d{2}/.*")
COMPANY_QR_PATTERN = re.compile(r".*_MIN.*")
TOL_MAP = {"J": 5, "F": 1}


# ============================================================================
# Shared helper: mantissa+exponent value code (e.g. "1001" -> 100 * 10^1 = 1000)
# ============================================================================
def value_from_fosan_r_notation(text: str):
    """R marks the decimal point, e.g. 22R0 -> 22.0, R2R00 -> 0.200, 0000 -> 0.0"""
    if text.isdigit():
        return float(text)
    if "R" in text:
        idx = text.index("R")
        new_text = text[:idx] + "." + text[idx + 1:]
        new_text = new_text.replace("R", "")
        try:
            return float(new_text)
        except ValueError:
            return None
    return None

def value_from_digits_WLSN(digits):
    digits = str(digits).strip()

    # 3-digit resistor marking
    # 151 -> 15 × 10^1 = 150
    # 222 -> 22 × 10^2 = 2200
    # 472 -> 47 × 10^2 = 4700
    if len(digits) == 3 and digits.isdigit():
        first_two = int(digits[:2])
        multiplier = int(digits[2])

        return first_two * (10 ** multiplier)

    # 4-digit resistor marking
    # 1001 -> 100 × 10^1 = 1000
    # 4701 -> 470 × 10^1 = 4700
    if len(digits) == 4 and digits.isdigit():
        first_three = int(digits[:3])
        multiplier = int(digits[3])

        return first_three * (10 ** multiplier)

    return digits
    
def find_fallback_qty(codes, current_code):
    """Looks for a separate bare-number barcode elsewhere in the same scan to use as qty."""
    for other in codes:
        if other.strip() != current_code and re.fullmatch(r"\d+", other.strip()):
            return int(other.strip())
    return None


def extract_actual_qty(company_qr: str):
    """
    Pulls the real quantity straight from the company QR itself, e.g.
    'PE11069A_1968_MIN/26-27/8035_1' -> 1968
    Returns None if the QR is missing or doesn't match the expected shape.
    """
    if not company_qr:
        return None
    match = re.match(r"^[A-Za-z0-9]+_(\d+)_MIN", company_qr)
    return int(match.group(1)) if match else None


def value_from_digits(digits: str):
    mantissa = int(digits[:-1])
    exponent = int(digits[-1])
    if len(digits) == 3:
        return (mantissa * 10 + exponent)/10
    return mantissa * (10 ** exponent)


# Engineering notation (e.g. "5K6" -> 5.6 * 1000 = 5600, "2K" -> 2000)
def value_from_engineering(text: str):
    multiplier = {"R": 1, "K": 1000, "M": 1_000_000}
    for letter, mult in multiplier.items():
        if letter in text:
            num_str = text.replace(letter, ".")
            return float(num_str) * mult
    return None


# ============================================================================
# Per-company parsers - each returns (npn, value, tol, qty) or None if no match
# ============================================================================
def parse_vikigs(codes):
    cr_code = kmb_code = qty_code = None
    tol_letter = None
    for c in codes:
        match = re.match(r"^CR-0\d([FJ])L7-+\S+$", c)
        if match:
            cr_code = c
            tol_letter = match.group(1)
        elif re.match(r"^KMB-\d{6,12}$", c):
            kmb_code = c
        elif re.fullmatch(r"\d+", c):
            qty_code = c

    if not cr_code:
        return None
    tol = TOL_MAP.get(tol_letter)
    value_text = cr_code.split("L7", 1)[1].strip("-")
    value = value_from_engineering(value_text)
    qty = int(qty_code) if qty_code else None

    return cr_code, value, tol, qty


def parse_hottech(codes):
    # Pass 1: code with quantity
    for c in codes:
        c = c.strip()

        match = re.match(
            r"^RI\d{4}L(\d{3,4})([FJ])T([&@])(\d+)$",
            c
        )

        if match:
            value_digits = match.group(1)
            tol_letter = match.group(2)
            qty = int(match.group(4))

            # J = 5% tolerance → always use 3 digits
            if tol_letter == "J" and len(value_digits) == 4:
                value_digits = value_digits[1:]

            value = value_from_digits_WLSN(value_digits)
            tol = TOL_MAP.get(tol_letter)
            if qty == 0 or qty is None:
                for x in codes:
                                if not x:
                                    continue
                
                                x = x.strip()
                
                                # Check 4 zeros FIRST
                                if "0000" in x:
                                    qty = 10000
                                    break
                
                                # Then check 3 zeros
                                elif "000" in x:
                                    qty = 5000
                                    break

            return c, value, tol, qty
        
    for c in codes:
            c = c.strip()
    
            match = re.match(
               r"^\d*RI\d{4}L(\d{3,4})([FJ])T.*",
                c
            )
    
            if match:
                value_digits = match.group(1)
                tol_letter = match.group(2)
                qty = None
    
                # J = 5% tolerance → always use 3 digits
                if tol_letter == "J" and len(value_digits) == 4:
                    value_digits = value_digits[1:]
    
                value = value_from_digits_WLSN(value_digits)
                tol = TOL_MAP.get(tol_letter)
                if qty == 0 or qty is None:
                    for x in codes:
                                    if not x:
                                        continue
                    
                                    x = x.strip()
                    
                                    # Check 4 zeros FIRST
                                    if "0000" in x:
                                        qty = 10000
                                        break
                    
                                    # Then check 3 zeros
                                    elif "000" in x:
                                        qty = 5000
                                        break
    
                return c, value, tol, qty
    
    # Pass 2: code without quantity
    for c in codes:
        c = c.strip()

        match = re.match(
            r"^RI\d{4}L(\d{3,4})([FJ])T([&@])",
            c
        )

        if match:
            value_digits = match.group(1)
            tol_letter = match.group(2)

            # J = 5% tolerance → always use 3 digits
            if tol_letter == "J" and len(value_digits) == 4:
                value_digits = value_digits[1:]

            value = value_from_digits_WLSN(value_digits)
            tol = TOL_MAP.get(tol_letter)
            qty = None

            for x in codes:
                if not x:
                    continue

                x = x.strip()

                # Check 4 zeros FIRST
                if "0000" in x:
                    qty = 10000
                    break

                # Then check 3 zeros
                elif "000" in x:
                    qty = 5000
                    break

            return c, value, tol, qty

    return None


def parse_fosan(codes):
    for c in codes:
        match = re.match(r"^FRC\d{3,4}([FJ])(\d{3,4})FT&(\d+)$", c)
        if match:
            value = value_from_digits(match.group(2))
            tol = TOL_MAP.get(match.group(1))
            qty = int(match.group(3))
            return c, value, tol, qty

        match = re.match(r"^FRC\d{3,4}([FJ])([0-9R]{3,6})TS$", c)
        if match:
            value = value_from_fosan_r_notation(match.group(2))
            tol = TOL_MAP.get(match.group(1))
            qty = find_fallback_qty(codes, c)
            return c, value, tol, qty

        match = re.match(r"^FRC\d{3,4}([FJ])(\d{3,4})\s*TS$", c)
        if match:
            value = value_from_digits_WLSN(match.group(2))
            print(value)
            tol = TOL_MAP.get(match.group(1))
            qty = find_fallback_qty(codes, c)
            return c, value, tol, qty

    return None


def parse_royalohm(codes):
    qty_suffix_map = {"5E": 5000, "CE": 10000}
    for c in codes:
        match = re.match(r"^\d{3,4}\s?[WS]\s?[A-Z0-9]{1,2}([FJ])\s?(\d{3,4})J?T\s?([0-9A-Z]E)$", c)
        if match:
            tol = TOL_MAP.get(match.group(1))
            value = value_from_digits(match.group(2))
            qty = qty_suffix_map.get(match.group(3))
            return c, value, tol, qty
    return None


def parse_walsin(codes):
    # Pass 1: find code containing quantity
    for c in codes:
        c = c.strip()

        match = re.match(
            r"^WR\d{2}X\s*(\d{3,4})\s*([FJ])TL\s*(\d+)$",
            c
        )

        if match:
            value_digits = match.group(1)
            tol_letter = match.group(2)
            qty = int(match.group(3))

            value = value_from_digits_WLSN(value_digits)
            tol = TOL_MAP.get(tol_letter)

            return c, value, tol, qty

    # Pass 2: code without quantity
    for c in codes:
        c = c.strip()

        match = re.match(
            r"^WR\d{2}X\s*(\d{3,4})\s*([FJ])TL",
            c
        )

        if match:
            value_digits = match.group(1)
            tol_letter = match.group(2)

            value = value_from_digits_WLSN(value_digits)
            tol = TOL_MAP.get(tol_letter)

            qty = find_fallback_qty(codes, c)

            return c, value, tol, qty

    return None


def parse_hkr(codes):
    for c in codes:
        if re.match(r"^\d{4}J\$", c):
            fields = [f.strip() for f in c.split("$")]
            value_text = fields[1] if len(fields) > 1 else ""
            value = value_from_engineering(value_text)
            tol = 5  # size+"J" prefix = 5%
            qty = None
            for f in fields[2:]:
                if re.fullmatch(r"\d+", f):
                    qty = int(f)
                    break
            return c, value, tol, qty
    return None


COMPANY_PARSERS = {
    "Vikings": parse_vikigs,
    "Hottech": parse_hottech,
    "Fosan": parse_fosan,
    "Royalohm": parse_royalohm,
    "Walsin": parse_walsin,
    "HKR": parse_hkr,
}


def process_scan(codes):
    """Returns (company_qr, make, npn, value, tol, qty) for the first company that matches."""
    company_qr = None
    for c in codes:
        if COMPANY_QR_PATTERN.match(c):
            company_qr = c
            break

    for company, parser in COMPANY_PARSERS.items():
        result = parser(codes)
        if result:
            npn, value, tol, qty = result
            return company_qr, company, npn, value, tol, qty

    return company_qr, None, None, None, None, None


def save_camera_data(text):
    _uuid = generate_uuid()
    codes = [line.strip() for line in text.splitlines() if line.strip()]

    company_qr, make, npn, value, tol, qty = process_scan(codes)
    if qty is None or qty < 500:
        for code in codes:
            if code.isdigit():
                code_val = int(code)
                if code_val < 500:
                    continue
                qty = code
                break

    actual_qty = extract_actual_qty(company_qr)

    if make is None:
        logger.warning(f"No known company matched for this scan: {codes}")

    # Code1 is always the company QR. Code2-Code12 get the remaining
    # scanned codes (everything except the QR itself), padded with None.
    other_codes = [c for c in codes if c != company_qr]
    codes_padded = [company_qr] + (other_codes + [None] * 11)[:11]

    query = """
    INSERT INTO CameraScanData (
        UUID, CreatedDate,
        Code1, Code2, Code3, Code4, Code5, Code6,
        Code7, Code8, Code9, Code10, Code11, Code12,
        MAKE, NPN, VALUE, TOL, QTY, ACTUALQTY, TYPE
    )
    VALUES (
        ?, GETDATE(),
        ?, ?, ?, ?, ?, ?,
        ?, ?, ?, ?, ?, ?,
        ?, ?, ?, ?, ?, ?, 'resistor'
    )
    """
    cursor.execute(query, [_uuid, *codes_padded, make, npn, value, tol, qty, actual_qty])
    conn.commit()
    logger.info(
        f"Saved UUID={_uuid} | Codes={codes_padded} | MAKE={make} | NPN={npn} | "
        f"VALUE={value} | TOL={tol} | QTY={qty} | ACTUALQTY={actual_qty}"
    )


def start_tcp_server():
    try:
        server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        server.bind((HOST, PORT))
        server.listen(5)
        logger.info(f"TCP Server started on {HOST}:{PORT}")

        while True:
            client, addr = server.accept()
            logger.info(f"Camera connected from {addr[0]}:{addr[1]}")
            threading.Thread(target=handle_client, args=(client, addr), daemon=True).start()
    except Exception as e:
        logger.exception(e)


def handle_client(client, addr):
    try:
        while True:
            data = client.recv(1024)
            if len(data) == 0:
                logger.warning("Camera closed the socket")
                break
            text = data.decode(errors="ignore")
            save_camera_data(text)
    except Exception as e:
        logger.exception(e)
    finally:
        client.close()


if __name__ == "__main__":
    start_tcp_server()