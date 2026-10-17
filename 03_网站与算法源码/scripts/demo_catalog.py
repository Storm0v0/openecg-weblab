"""Single catalogue for the twenty fixed public ECG demonstrations.

Each tuple is (dataset, record, lead, annotation, start_second, label).
New records are consecutive/explicit record IDs, not selected using predictions.
The ten-second QTDB window defaults to 600 s; see WINDOW_SELECTION for any
annotation-availability adjustment. The original four selections stay unchanged.
"""

ORIGINAL_RECORD_IDS = ("ludb-16", "ludb-1", "qtdb-sel100", "qtdb-sel103")

RECORDS = (
    ("ludb", "16", "ii", "ii", 0, "LUDB 16 · Lead II"),
    ("ludb", "1", "ii", "ii", 0, "LUDB 01 · Lead II"),
    ("ludb", "2", "ii", "ii", 0, "LUDB 02 · Lead II"),
    ("ludb", "3", "ii", "ii", 0, "LUDB 03 · Lead II"),
    ("ludb", "4", "ii", "ii", 0, "LUDB 04 · Lead II"),
    ("ludb", "5", "ii", "ii", 0, "LUDB 05 · Lead II"),
    ("ludb", "6", "ii", "ii", 0, "LUDB 06 · Lead II"),
    ("ludb", "7", "ii", "ii", 0, "LUDB 07 · Lead II"),
    ("ludb", "8", "ii", "ii", 0, "LUDB 08 · Lead II"),
    ("ludb", "9", "ii", "ii", 0, "LUDB 09 · Lead II"),
    ("qtdb", "sel100", "MLII", "q1c", 600, "QTDB sel100 · MLII"),
    ("qtdb", "sel103", "MLII", "q1c", 600, "QTDB sel103 · MLII"),
    ("qtdb", "sel114", "MLII", "q1c", 600, "QTDB sel114 · MLII"),
    ("qtdb", "sel116", "MLII", "q1c", 600, "QTDB sel116 · MLII"),
    ("qtdb", "sel117", "MLII", "q1c", 600, "QTDB sel117 · MLII"),
    ("qtdb", "sel123", "MLII", "q1c", 600, "QTDB sel123 · MLII"),
    ("qtdb", "sel213", "MLII", "q1c", 600, "QTDB sel213 · MLII"),
    ("qtdb", "sel221", "MLII", "q1c", 600, "QTDB sel221 · MLII"),
    ("qtdb", "sel230", "MLII", "q1c", 600, "QTDB sel230 · MLII"),
    ("qtdb", "sel231", "MLII", "q1c", 600, "QTDB sel231 · MLII"),
)

WINDOW_SELECTION = {
    "duration_seconds": 10,
    "original_records": "Original four windows are retained without modification.",
    "new_ludb": "Records 2 through 9, complete 0-10 s Lead II records.",
    "new_qtdb": "Explicit sel114, sel116, sel117, sel123, sel213, sel221, sel230, sel231; use MLII, start at 600 s when q1c contains a complete annotated interval. No selection uses model outputs or accuracy.",
    "record_substitution": "sel115 does not occur in official QTDB RECORDS or SHA256SUMS.txt. Use sel213, which exists in the official database and has MLII, instead; this is unrelated to model performance.",
    "extension_to_twenty": {
        "retained": "The previous fourteen records and all their windows remain unchanged.",
        "ludb": "Add the next consecutive records 7, 8, 9, using Lead II and the full 0-10 s records.",
        "qtdb": "Consider explicit next records sel221, sel223, sel230. sel223 has no complete q1c interval at 600-610 s, so use the next ID sel231. sel221, sel230 and sel231 all have MLII and complete q1c intervals at 600-610 s. Selection is based only on official availability, lead and annotation coverage, never model predictions.",
    },
    "adjustments": {},
}
