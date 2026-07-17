import re

from langchain_text_splitters import RecursiveCharacterTextSplitter

from rag_chat.services.embedding_service import model as _embedding_model
from rag_chat.services.game_detector import detect_game, get_known_game_names

# A game-level rulebook in this corpus always restarts at "1. Introduction",
# so that marks the boundary between one game's section and the next.
_GAME_BOUNDARY = re.compile(r"^1\.\s+Introduction\s*$", re.MULTILINE)

# Matches numbered section headings like "6. Number of Players" or
# "182. Matchmaking Rating (MMR)" but not numbered list items like
# "1. Boarding the transport aircraft." (real headings don't end in a
# period, ordinary list items do).
_SECTION_HEADING = re.compile(r"(?=^\d+\.\s+[A-Z][^.\n]{1,60}\s*\n)", re.MULTILINE)
_HEADING_TITLE = re.compile(r"^(\d+\.\s+[A-Z][^.\n]{1,60})\s*\n")

_PAGE_MARKER = re.compile(r"PAGE (\d+)")

_MIN_CHUNK_SIZE = 20
_MIN_HEADINGS_FOR_STRUCTURED_SPLIT = 2

# One chunk per heading is the target. Verified across all 1,035 headings in
# the source rulebook: the longest is ~490 tokens, so this threshold rarely
# triggers on this document - it exists for headings (or documents) that run
# longer than this corpus does.
_HEADING_SPLIT_THRESHOLD = 700
_SPLIT_CHUNK_TOKENS = 700
_SPLIT_CHUNK_OVERLAP = 100


def _token_length(text):
    return len(_embedding_model.tokenizer.encode(text, add_special_tokens=False))


_oversized_heading_splitter = RecursiveCharacterTextSplitter(
    chunk_size=_SPLIT_CHUNK_TOKENS,
    chunk_overlap=_SPLIT_CHUNK_OVERLAP,
    length_function=_token_length,
    separators=["\n\n", "\n", " ", ""],
)


def _split_into_game_sections(text):
    boundaries = [m.start() for m in _GAME_BOUNDARY.finditer(text)]
    if len(boundaries) < 2:
        return [text]

    sections = []
    for i, start in enumerate(boundaries):
        end = boundaries[i + 1] if i + 1 < len(boundaries) else len(text)
        sections.append(text[start:end])

    if boundaries[0] > 0:
        sections[0] = text[: boundaries[0]] + sections[0]

    return sections


def _extract_heading_title(piece):
    match = _HEADING_TITLE.match(piece)
    return match.group(1).strip() if match else None


def _strip_page_markers(text):
    cleaned = _PAGE_MARKER.sub("", text)
    return re.sub(r"\n{3,}", "\n\n", cleaned).strip()


def _split_section_into_headings(section_text):
    raw_pieces = [s.strip() for s in _SECTION_HEADING.split(section_text) if len(s.strip()) >= _MIN_CHUNK_SIZE]

    if len(raw_pieces) < _MIN_HEADINGS_FOR_STRUCTURED_SPLIT:
        # No heading structure detected in this section (e.g. a cover
        # page/TOC before the first real heading) - treat it as a single
        # untitled piece so it still goes through the same size-based
        # splitting as every other heading below.
        stripped = section_text.strip()
        return [(None, stripped)] if stripped else []

    return [(_extract_heading_title(piece), piece) for piece in raw_pieces]


def split_text_into_chunks(text):
    known_names = get_known_game_names()
    game_sections = _split_into_game_sections(text)

    chunks = []
    for section in game_sections:
        game_name = detect_game(section, known_names)
        headings = _split_section_into_headings(section)

        # A heading doesn't always contain its own "PAGE N" marker - if it
        # started mid-page, the marker was consumed by an earlier heading. So
        # page_start carries forward whatever page we were last on, and only
        # advances when this piece actually crosses into a new page.
        current_page = None
        for title, heading_piece in headings:
            pages_in_piece = [int(m.group(1)) for m in _PAGE_MARKER.finditer(heading_piece)]
            page_start = current_page if current_page is not None else (pages_in_piece[0] if pages_in_piece else None)
            if pages_in_piece:
                current_page = pages_in_piece[-1]
            page_end = current_page

            cleaned = _strip_page_markers(heading_piece)
            if not cleaned:
                continue

            breadcrumb = f"[{game_name}] " if game_name else ""

            if _token_length(cleaned) <= _HEADING_SPLIT_THRESHOLD:
                chunks.append({
                    "text": breadcrumb + cleaned,
                    "game_name": game_name,
                    "heading": title,
                    "subheading": None,
                    "page_start": page_start,
                    "page_end": page_end,
                })
            else:
                # Only this one oversized heading gets sub-split - every
                # other heading in the document still becomes exactly one
                # chunk.
                sub_pieces = _oversized_heading_splitter.split_text(cleaned)
                total = len(sub_pieces)
                for i, sub_piece in enumerate(sub_pieces, 1):
                    chunks.append({
                        "text": breadcrumb + sub_piece,
                        "game_name": game_name,
                        "heading": title,
                        "subheading": f"part {i} of {total}",
                        "page_start": page_start,
                        "page_end": page_end,
                    })

    return chunks
