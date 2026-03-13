import pandas as pd

books = pd.read_csv("books.csv")
ratings = pd.read_csv("ratings.csv")

print("Books:", books.shape)
print("Ratings:", ratings.shape)

selected_users = ratings["user_id"].unique()[:6]

ratings_6 = ratings[ratings["user_id"].isin(selected_users)]

book_ids = ratings_6["book_id"].unique()

books_6 = books[books["book_id"].isin(book_ids)]

books_6.to_csv("books_6users.csv", index=False)
ratings_6.to_csv("ratings_6users.csv", index=False)

print("New books dataset:", books_6.shape)
print("New ratings dataset:", ratings_6.shape)