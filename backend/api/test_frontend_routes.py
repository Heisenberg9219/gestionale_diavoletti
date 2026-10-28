"""Controlla che ogni chiamata del frontend arrivi a un indirizzo esistente.

Il test legge i sorgenti React, estrae le chiamate scritte con un indirizzo
fisso (``request("/...")``, ``downloadFile(`/...`)``) e verifica che il backend:

- abbia una rotta per quell'indirizzo;
- accetti il metodo HTTP usato (ad esempio niente POST su un elenco di sola
  lettura).

Errori come quello del reso (POST su ``/returns/returns/`` invece di
``create-draft``) vengono così fermati dai test prima del deploy.
"""

import re
from pathlib import Path

from unittest import skipUnless

from django.test import SimpleTestCase
from django.urls import Resolver404, resolve

FRONTEND_SRC = Path(__file__).resolve().parents[2] / "frontend" / "src"
CALL = re.compile(r"\b(request|downloadFile|authorizedFetch)\(\s*([`\"])(/[^`\"]*)\2")
NEXT_CALL = re.compile(r"\b(request|downloadFile|authorizedFetch)\(")
METHOD = re.compile(r"\bmethod:\s*(?:[\w.]+\s*\?\s*)?\"([A-Z]+)\"(?:\s*:\s*\"([A-Z]+)\")?")
PLACEHOLDER = re.compile(r"\$\{[^}]*\}")
SAMPLE_ID = "00000000-0000-0000-0000-000000000000"


def frontend_calls():
    for source in sorted(FRONTEND_SRC.rglob("*.js*")):
        text = source.read_text(encoding="utf-8")
        for match in CALL.finditer(text):
            # Le opzioni della chiamata stanno subito dopo l'indirizzo,
            # prima della chiamata successiva.
            tail = text[match.end():match.end() + 400]
            following = NEXT_CALL.search(tail)
            if following:
                tail = tail[:following.start()]
            method = METHOD.search(tail)
            methods = [m for m in method.groups() if m] if method else ["GET"]
            line = text.count("\n", 0, match.start()) + 1
            yield f"{source.relative_to(FRONTEND_SRC)}:{line}", match.group(3), methods


# Nell'immagine Docker del backend il frontend non c'è: lì il test si salta,
# mentre nei test su GitHub il repository è completo.
@skipUnless(FRONTEND_SRC.is_dir(), "sorgenti del frontend non presenti")
class FrontendRoutesTests(SimpleTestCase):
    def test_frontend_sources_are_available(self):
        self.assertGreater(len(list(frontend_calls())), 50)

    def test_every_frontend_call_reaches_an_existing_route_and_method(self):
        problems = []
        for where, raw_path, methods in frontend_calls():
            path = PLACEHOLDER.sub(SAMPLE_ID, raw_path.split("?")[0])
            if not path.endswith("/"):
                path += "/"
            try:
                match = resolve(f"/api/v1{path}")
            except Resolver404:
                problems.append(f"{where}: {raw_path} non esiste nel backend")
                continue
            actions = getattr(match.func, "actions", None)
            view_class = getattr(match.func, "cls", None) or getattr(match.func, "view_class", None)
            for method in methods:
                if actions is not None:
                    allowed = method.lower() in actions
                elif view_class is not None:
                    allowed = hasattr(view_class, method.lower())
                else:
                    allowed = True
                if not allowed:
                    problems.append(f"{where}: {method} {raw_path} non è consentito dal backend")
        self.assertEqual(problems, [], "\n" + "\n".join(problems))
