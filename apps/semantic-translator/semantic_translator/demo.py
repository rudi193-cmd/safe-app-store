"""Built-in bilingual demo corpus — seeds data/corpus.jsonl with no network.

The scraper needs `gh` and GitHub API access; this gives the app real
EN/ES content anywhere, so Search, Learn, and Play work out of the box.
Segments follow the scraper's schema, and lessons carry "bilingual" in
their id so learn._load_bilingual_pairs() pairs them by position.
"""
from __future__ import annotations

import json
import pathlib

# (lesson_id, grade, subject, [(en, es), ...]) — EN/ES order within a
# lesson must stay aligned: learn.py pairs en[i] with es[i].
_LESSONS: list[tuple[str, str, str, list[tuple[str, str]]]] = [
    (
        "demo-what-is-ai-bilingual", "6-8", "AI Literacy",
        [
            ("Artificial intelligence is a computer system that learns patterns from examples instead of following fixed rules.",
             "La inteligencia artificial es un sistema informático que aprende patrones a partir de ejemplos en lugar de seguir reglas fijas."),
            ("A model does not understand the world; it predicts what usually comes next.",
             "Un modelo no entiende el mundo; predice lo que suele venir después."),
            ("Training data is the collection of examples a model learns from.",
             "Los datos de entrenamiento son la colección de ejemplos de los que aprende un modelo."),
            ("If the examples are biased, the model's answers will be biased too.",
             "Si los ejemplos están sesgados, las respuestas del modelo también estarán sesgadas."),
            ("Always ask: who built this system, and what was it built to do?",
             "Pregunta siempre: ¿quién construyó este sistema y para qué fue construido?"),
        ],
    ),
    (
        "demo-thinking-with-machines-bilingual", "6-8", "AI Literacy",
        [
            ("A chatbot can sound confident even when it is wrong.",
             "Un chatbot puede sonar seguro incluso cuando se equivoca."),
            ("Verify important claims with a source you trust before you share them.",
             "Verifica las afirmaciones importantes con una fuente de confianza antes de compartirlas."),
            ("Good questions get better answers; details give the machine direction.",
             "Las buenas preguntas obtienen mejores respuestas; los detalles le dan dirección a la máquina."),
            ("The machine is a tool for your thinking, not a replacement for it.",
             "La máquina es una herramienta para tu pensamiento, no un reemplazo."),
            ("When you copy an answer without reading it, you learn nothing.",
             "Cuando copias una respuesta sin leerla, no aprendes nada."),
        ],
    ),
    (
        "demo-data-and-you-bilingual", "6-8", "Digital Citizenship",
        [
            ("Everything you type into an app may become data about you.",
             "Todo lo que escribes en una aplicación puede convertirse en datos sobre ti."),
            ("Privacy means you decide who can see your information.",
             "La privacidad significa que tú decides quién puede ver tu información."),
            ("A strong password is long, unique, and never shared.",
             "Una contraseña fuerte es larga, única y nunca se comparte."),
            ("Free services often pay for themselves with your attention and your data.",
             "Los servicios gratuitos a menudo se pagan con tu atención y tus datos."),
            ("Before you post, imagine the whole school reading it tomorrow.",
             "Antes de publicar, imagina que toda la escuela lo leerá mañana."),
        ],
    ),
]


def demo_segments() -> list[dict]:
    segments: list[dict] = []
    for lesson_id, grade, subject, pairs in _LESSONS:
        i = 0
        for en, es in pairs:
            for lang, text in (("en", en), ("es", es)):
                segments.append({
                    "id": f"{lesson_id}::{i}",
                    "lesson": lesson_id,
                    "grade": grade,
                    "subject": subject,
                    "is_bilingual": True,
                    "lang": lang,
                    "text": text,
                })
                i += 1
    return segments


def seed_demo(output_path: str = "data/corpus.jsonl", force: bool = False) -> int:
    """Write the demo corpus. Refuses to overwrite an existing corpus unless force."""
    out = pathlib.Path(output_path)
    if out.exists() and not force:
        raise FileExistsError(
            f"{out} already exists — use --force to overwrite it with the demo corpus"
        )
    out.parent.mkdir(parents=True, exist_ok=True)
    segments = demo_segments()
    with open(out, "w", encoding="utf-8") as f:
        for seg in segments:
            f.write(json.dumps(seg, ensure_ascii=False) + "\n")
    pairs = len(segments) // 2
    print(f"Seeded demo corpus: {out}")
    print(f"  {len(segments)} segments · {len(_LESSONS)} lessons · {pairs} EN/ES pairs")
    print("Try:  semantic-translator play")
    return len(segments)
