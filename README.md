# resistors_pattern_detection
## Database Schema

**Database:** `test` (SQL Server LocalDB — `(localdb)\MSSQLLocalDB`)
**Table:** `dbo.CameraScanData`

| Column      | Type                | Description                                                        |
|-------------|---------------------|----------------------------------------------------------------------|
| Id          | INT (identity, PK)  | Auto-incrementing primary key                                      |
| UUID        | (assumed VARCHAR)   | Unique ID generated per scan trigger                                |
| CreatedDate | DATETIME            | Timestamp of the scan, set via `GETDATE()`                          |
| Code1       | VARCHAR             | Company QR (always the `_MIN/YY-YY/` pattern code)                  |
| Code2-Code12| VARCHAR             | Remaining raw scanned codes from the camera, in scan order          |
| MAKE        | VARCHAR(50)         | Detected component vendor (Vikigs / Hottech / Fosan / Royalohm / Walsin / HKR) |
| NPN         | VARCHAR(200)        | The specific vendor code matched to identify MAKE                   |
| VALUE       | VARCHAR(50)         | Calculated resistance value (Ohms), parsed from NPN                 |
| TOL         | VARCHAR(10)         | Tolerance percentage (1 or 5)                                       |
| QTY         | VARCHAR(20)         | Quantity, parsed from NPN or a separate barcode                     |
| TYPE        | VARCHAR(50)         | Component type (currently always `'resistor'`)                     |
| ACTUALQTY   | INT                 | True quantity extracted directly from the company QR itself         |
