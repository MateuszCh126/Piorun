import json
import os
import core.brain as brain

# KONFIGURACJA
CHUNK_DURATION = 300  # 5 minut w sekundach


def split_transcript_into_chunks(transcript, chunk_duration=CHUNK_DURATION):
    """Dzieli segmenty transkrypcji na fragmenty o zadanej dlugosci (czysta funkcja)."""
    chunks = []
    current_chunk = []
    current_start = 0

    for seg in transcript:
        if seg['end'] > current_start + chunk_duration:
            if current_chunk:
                chunks.append({
                    "start": current_start,
                    "end": current_chunk[-1]['end'],
                    "text": " ".join([s['text'] for s in current_chunk])
                })
            current_start = seg['start']
            current_chunk = [seg]
        else:
            current_chunk.append(seg)

    if current_chunk:
        chunks.append({
            "start": current_start,
            "end": transcript[-1]['end'],
            "text": " ".join([s['text'] for s in current_chunk])
        })
    return chunks


def pick_slide_for_chunk(slides, chunk_start, chunk_end):
    """Zwraca ostatni slajd wyswietlony przed polowa fragmentu (czysta funkcja)."""
    mid_time = (chunk_start + chunk_end) / 2
    best_slide = None
    for s in slides:
        if s['timestamp'] <= mid_time:
            best_slide = s['file']
    return best_slide


def generate_academic_notes(session_dir, subject):
    transcript_path = os.path.join(session_dir, "transcript.json")
    timeline_path = os.path.join(session_dir, "slides_timeline.json")
    output_path = os.path.join(session_dir, "notes_structured.json")

    if not os.path.exists(transcript_path):
        return f"Błąd: Brak transkrypcji w {session_dir}"

    print(f"[*] Rozpoczynanie generowania notatek dla: {subject}")
    
    with open(transcript_path, 'r', encoding='utf-8') as f:
        transcript = json.load(f)
    
    slides = []
    if os.path.exists(timeline_path):
        with open(timeline_path, 'r', encoding='utf-8') as f:
            slides = json.load(f)

    # 1. Podział na Chunki
    chunks = split_transcript_into_chunks(transcript, CHUNK_DURATION)

    # 2. Przetwarzanie przez Pioruna
    structured_notes = []
    previous_summary = ""

    for idx, chunk in enumerate(chunks):
        print(f"[*] Przetwarzanie części {idx+1}/{len(chunks)} ({chunk['start']}s - {chunk['end']}s)...")
        
        # Znajdź slajd dla tej części (ostatni wyświetlony przed połową chunku)
        best_slide = pick_slide_for_chunk(slides, chunk['start'], chunk['end'])
        
        prompt = build_prompt(chunk['text'], previous_summary, best_slide)
        
        # Wywołanie Mózgu Pioruna (bezpośrednio przez execute_brain_loop z historii)
        history = [
            {"role": "system", "content": brain.get_system_prompt()},
            {"role": "user", "content": prompt}
        ]
        
        # Piorun myśli...
        updated_history = brain.execute_brain_loop(history, f"academic_{subject}", topic=f"Notatki {subject}")
        ai_response = ""
        for msg in reversed(updated_history):
            content = msg.get("content") if isinstance(msg, dict) else getattr(msg, "content", None)
            role = msg.get("role") if isinstance(msg, dict) else getattr(msg, "role", None)
            if role == "assistant" and content:
                ai_response = content
                break

        # Ekstrakcja podsumowania dla następnej partii (szukamy sekcji Podsumowanie)
        # To jest uproszczone, Piorun dba o format Markdown
        previous_summary = ai_response.split("Podsumowanie tej części")[-1] if "Podsumowanie tej części" in ai_response else ""

        structured_notes.append({
            "chunk_index": idx,
            "time_start": int(chunk['start']),
            "time_end": int(chunk['end']),
            "slide": best_slide,
            "notes_markdown": ai_response
        })

    # 3. Zapisz wynik
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(structured_notes, f, ensure_ascii=False, indent=2)

    print(f"[OK] Notatki ustrukturyzowane zapisane: {output_path}")
    return output_path

def build_prompt(text, prev_context, slide):
    context_str = f"\n[KONTEKST POPRZEDNIEJ CZĘŚCI]:\n{prev_context}\n" if prev_context else ""
    slide_str = f"\n[WIZUALIZACJA]: Na ekranie wyświetlany jest slajd: {os.path.basename(slide)}\n" if slide else ""
    
    return f"""Jako Piorun ⚡ Academic Mode, przygotuj profesjonalne notatki z fragmentu wykładu.
{context_str}{slide_str}
[TRANSKRYPCJA]:
{text}

WYMAGANIA:
- Nagłówek poziomu 2 z tytułem sekcji.
- Lista kluczowych pojęć (boldem) i ich definicje.
- Sekcja 'Ważne informacje' (punkty, wzory, fakty).
- Sekcja 'Pytania kontrolne' (2-3 pytania sprawdzające wiedzę).
- Sekcja 'Podsumowanie tej części' (krótki opis 2-3 zdania).

Całość napisz czystym Markdownem, bez zbędnych komentarzy.
"""

if __name__ == "__main__":
    import sys
    if len(sys.argv) < 3:
        print("Użycie: python note_generator.py [ścieżka_do_sesji] [temat]")
    else:
        generate_academic_notes(sys.argv[1], sys.argv[2])
