import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from radar import overlay
from radar.befehle import ausfuehren


class BefehleTest(unittest.TestCase):
    def test_neu_laden_aendert_dasselbe_dict(self):
        with tempfile.TemporaryDirectory() as d:
            datei = Path(d) / "aion2-radar.json"
            with mock.patch.object(overlay, "KONFIG", datei), mock.patch.object(overlay, "_konfig", None):
                k = overlay.konfig_laden()
                datei.write_text(json.dumps({"groesse": 300}))
                overlay.konfig_neu_laden()
                self.assertEqual(k["groesse"], 300)
                self.assertEqual(k["reichweite"], 150)  # Standardwert bleibt
                self.assertIs(overlay.konfig_laden(), k)

    def test_bekannter_befehl_ruft_aktion(self):
        aufrufe = []
        ausfuehren("ton_testen\n", {"ton_testen": lambda: aufrufe.append(1)})
        self.assertEqual(aufrufe, [1])

    def test_unbekannter_befehl_wird_ignoriert(self):
        ausfuehren("quatsch", {"ton_testen": self.fail})


if __name__ == "__main__":
    unittest.main()
