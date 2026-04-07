import joblib
import pandas as pd
import ast
from sklearn.metrics.pairwise import cosine_similarity

# load model
from pathlib import Path
from database import connect

model_path = Path(__file__).resolve().parents[1] / "model" / "hybrid_model.pkl"
if not model_path.exists():
    raise FileNotFoundError(f"Hybrid model not found at: {model_path}")

model = joblib.load(model_path)

books = model["books"]
ratings = model["ratings"]
content_similarity = model["content_similarity"]

# build user-item matrix
user_book_matrix = ratings.pivot_table(
    index="user_id",
    columns="book_id",
    values="rating"
).fillna(0)

# user similarity (collaborative filtering)
user_similarity = cosine_similarity(user_book_matrix)


def _normalize_title(value):
    return " ".join(str(value or "").strip().lower().split())


_book_metadata_by_normalized_title = {}
for _, _row in books.iterrows():
    _title = _row.get("title", "")
    _normalized = _normalize_title(_title)
    if not _normalized or _normalized in _book_metadata_by_normalized_title:
        continue

    _author = _row.get("author")
    if _author is None or str(_author).strip() == "":
        _author = _row.get("authors", "")

    _book_metadata_by_normalized_title[_normalized] = {
        "book_id": str(_row.get("book_id") or "").strip(),
        "title": str(_title or "").strip(),
        "authors": str(_author or "").strip(),
        "description": str(_row.get("description") or "").strip(),
        "genres": str(_row.get("genres") or "").strip(),
        "cover_img": str(_row.get("cover_img") or _row.get("coverImg") or "").strip(),
    }


def get_book_metadata_for_title(title):
    """Return best-effort metadata from trained catalog for a given title."""
    return _book_metadata_by_normalized_title.get(_normalize_title(title), {})


def _get_user_books_from_db(user_id):
    """
    Return a dict of {book_id (int): rating (int)} from the live SQLite bookshelf.
    Also returns a set of book_id integers the user has already read.
    """
    conn = connect()
    cursor = conn.cursor()
    cursor.execute(
        "SELECT book_id, COALESCE(rating, 0) FROM bookshelf WHERE user_id = %s",
        (user_id,),
    )
    rows = cursor.fetchall()
    conn.close()

    user_ratings = {}
    for book_id_raw, rating in rows:
        try:
            user_ratings[int(book_id_raw)] = int(rating)
        except (ValueError, TypeError):
            pass

    return user_ratings


def _get_user_preferences_from_db(user_id):
    conn = connect()
    cursor = conn.cursor()
    cursor.execute(
        "SELECT favorite_genre, favorite_author FROM users WHERE id = %s",
        (user_id,),
    )
    row = cursor.fetchone()
    conn.close()

    if not row:
        return "", ""

    favorite_genre = (row[0] or "").strip()
    favorite_author = (row[1] or "").strip()
    return favorite_genre, favorite_author


def _extract_genre_tokens(raw_genres):
    if raw_genres is None:
        return []

    if isinstance(raw_genres, list):
        return [str(item).strip().lower() for item in raw_genres if str(item).strip()]

    text = str(raw_genres).strip()
    if not text:
        return []

    if text.startswith("[") and text.endswith("]"):
        try:
            parsed = ast.literal_eval(text)
            if isinstance(parsed, list):
                return [str(item).strip().lower() for item in parsed if str(item).strip()]
        except (ValueError, SyntaxError):
            pass

    return [
        part.strip().strip("'\"").lower()
        for part in text.strip("[]").split(",")
        if part.strip().strip("'\"")
    ]


def _book_author_text(book_row):
    author = book_row.get("author")
    if author is None or str(author).strip() == "":
        author = book_row.get("authors", "")
    return str(author).lower()


def _primary_genre_token(raw_genres):
    tokens = _extract_genre_tokens(raw_genres)
    return tokens[0] if tokens else ""


def _genre_match_score(preferred_genre, raw_genres):
    if not preferred_genre:
        return 0.0

    tokens = _extract_genre_tokens(raw_genres)
    if not tokens:
        return 0.0

    if preferred_genre == tokens[0]:
        return 2.0

    if preferred_genre in tokens[1:]:
        return 0.5

    return 0.0


def _cold_start_recommend(user_id, top_n=5, exclude_book_ids=None):
    if exclude_book_ids is None:
        exclude_book_ids = set()

    preferred_genre, preferred_author = _get_user_preferences_from_db(user_id)
    preferred_genre = preferred_genre.lower()
    preferred_author = preferred_author.lower()

    ranked = []

    for _, row in books.iterrows():
        book_id = row.get("book_id")
        if book_id in exclude_book_ids:
            continue

        score = 0.0

        if preferred_genre:
            score += _genre_match_score(preferred_genre, row.get("genres", ""))

        if preferred_author:
            author_text = _book_author_text(row)
            if preferred_author in author_text:
                score += 4.0

        if score > 0:
            ranked.append((book_id, score))

    if not ranked:
        return []

    ranked = sorted(ranked, key=lambda x: x[1], reverse=True)

    recommendations = []
    for book_id, _ in ranked:
        title_matches = books[books["book_id"] == book_id]["title"].values
        if len(title_matches) == 0:
            continue
        recommendations.append(title_matches[0])
        if len(recommendations) == top_n:
            break

    return recommendations


def _compute_hybrid_scores(user_id):

    # ---------- LIVE SHELF ----------
    # Pull what THIS user has actually read/rated from SQLite bookshelf
    user_ratings_db = _get_user_books_from_db(user_id)
    user_book_ids_read = set(user_ratings_db.keys())

    # Cold-start: no live reading history yet, use registration preferences only.
    if not user_ratings_db:
        return None, user_book_ids_read

    # ---------- CONTENT SCORE ----------
    content_scores = {}

    for book_id, rating in user_ratings_db.items():
        index = books[books["book_id"] == book_id].index

        if len(index) == 0:
            continue

        idx = index[0]
        similarities = list(enumerate(content_similarity[idx]))

        for i, score in similarities:
            bid = books.iloc[i]["book_id"]
            # Weight similarity by the user's own rating for this book
            content_scores[bid] = content_scores.get(bid, 0) + score * (rating / 5.0)

    # ---------- COLLABORATIVE SCORE ----------
    # Use the pre-trained user-item matrix; if the user exists in it use their
    # row's similarity, otherwise skip collaborative filtering gracefully
    collaborative_scores = {}

    if user_id in user_book_matrix.index:
        user_index = user_book_matrix.index.get_loc(user_id)
        similar_users = list(enumerate(user_similarity[user_index]))
        similar_users = sorted(similar_users, key=lambda x: x[1], reverse=True)[1:4]

        for u, sim in similar_users:
            similar_user_id = user_book_matrix.index[u]
            books_liked = ratings[ratings["user_id"] == similar_user_id]

            for _, row in books_liked.iterrows():
                bid = row["book_id"]
                collaborative_scores[bid] = (
                    collaborative_scores.get(bid, 0) + sim * row["rating"]
                )

    # ---------- COMBINE BOTH ----------
    final_scores = {}

    for book_id in books["book_id"]:
        content = content_scores.get(book_id, 0)
        collaborative = collaborative_scores.get(book_id, 0)
        final_scores[book_id] = 0.6 * content + 0.4 * collaborative

    return final_scores, user_book_ids_read


def hybrid_recommend_score_map(user_id, exclude_read=True):
    """
    Return per-book hybrid scores for the given user.
    Keys are book_id as strings, values are raw hybrid scores.
    """
    final_scores, user_book_ids_read = _compute_hybrid_scores(user_id)

    if final_scores is None:
        # Cold start path: approximate scores from the same preference signals.
        preferred_genre, preferred_author = _get_user_preferences_from_db(user_id)
        preferred_genre = preferred_genre.lower()
        preferred_author = preferred_author.lower()

        fallback_scores = {}
        for _, row in books.iterrows():
            book_id = row.get("book_id")
            if exclude_read and book_id in user_book_ids_read:
                continue

            score = 0.0
            if preferred_genre:
                score += _genre_match_score(preferred_genre, row.get("genres", ""))

            if preferred_author:
                author_text = _book_author_text(row)
                if preferred_author in author_text:
                    score += 4.0

            fallback_scores[str(book_id)] = float(score)

        return fallback_scores

    score_map = {}
    for book_id, score in final_scores.items():
        if exclude_read and book_id in user_book_ids_read:
            continue
        score_map[str(book_id)] = float(score)

    return score_map


def hybrid_recommend(user_id, top_n=5):
    final_scores, user_book_ids_read = _compute_hybrid_scores(user_id)

    if final_scores is None:
        return _cold_start_recommend(
            user_id,
            top_n=top_n,
            exclude_book_ids=user_book_ids_read,
        )

    recommended = sorted(final_scores.items(), key=lambda x: x[1], reverse=True)

    recommended_books = []

    for book_id, _ in recommended:
        # Skip books already on this user's live shelf
        if book_id in user_book_ids_read:
            continue

        title_matches = books[books["book_id"] == book_id]["title"].values
        if len(title_matches) == 0:
            continue

        recommended_books.append(title_matches[0])

        if len(recommended_books) == top_n:
            break

    return recommended_books

if __name__ == "__main__":
    sample_user_id = int(ratings["user_id"].iloc[0])
    print(f"Running recommendations for user_id={sample_user_id}")

    results = hybrid_recommend(sample_user_id, top_n=5)

    for r in results:
        print(r)

