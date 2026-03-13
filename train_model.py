import pandas as pd
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity
import joblib

# ===============================
# Load datasets
# ===============================

books = pd.read_csv("books_6users.csv")
ratings = pd.read_csv("ratings_6users.csv")

print("Books loaded:", books.shape)
print("Ratings loaded:", ratings.shape)

# ===============================
# Content-Based Filtering
# ===============================

books["content"] = (
    books["title"].fillna("") + " " +
    books["author"].fillna("") + " " +
    books["description"].fillna("")
)

tfidf = TfidfVectorizer(stop_words="english")

tfidf_matrix = tfidf.fit_transform(books["content"])

content_similarity = cosine_similarity(tfidf_matrix, tfidf_matrix)

print("Content similarity matrix created")

# ===============================
# Collaborative Filtering
# ===============================

user_book_matrix = ratings.pivot_table(
    index="user_id",
    columns="book_id",
    values="rating"
).fillna(0)

user_similarity = cosine_similarity(user_book_matrix)

print("User similarity matrix created")

# ===============================
# Save Hybrid Model
# ===============================

model_data = {
    "books": books,
    "ratings": ratings,
    "content_similarity": content_similarity,
    "user_similarity": user_similarity
}

joblib.dump(model_data, "hybrid_model.pkl")

print("Hybrid model saved successfully!")