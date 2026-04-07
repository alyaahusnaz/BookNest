from recommender.recommender import hybrid_recommend, books, ratings
from database import connect
import pandas as pd

conn = connect()
cur = conn.cursor()
cur.execute('SELECT id, username FROM users')
rows = cur.fetchall()
conn.close()

user_map = {int(r[0]): r[1] for r in rows}
existing = set(user_map.keys())

r = ratings.copy()
r = r[r['user_id'].isin(existing)]

# treat rating >=3 as liked
liked = r[r['rating'] >= 3]
book_title = {int(row.book_id): str(row.title) for row in books[['book_id', 'title']].dropna().itertuples(index=False)}

book_author = {}
for row in books.itertuples(index=False):
    bid = int(row.book_id)
    auth = row.author if hasattr(row, 'author') else ''
    book_author[bid] = str(auth or '')

print('Examples: if A reads book by author X, does system recommend other books by X to A?')
print()

for user_id in sorted(existing):
    un = user_map[user_id]
    u_liked = set(liked[liked['user_id'] == user_id]['book_id'].astype(int).tolist())
    if not u_liked:
        continue
    
    recs = hybrid_recommend(user_id, top_n=20)
    matches = []
    
    for liked_bid in list(u_liked)[:5]:
        author = book_author.get(liked_bid, '').split(',')[0].strip()
        if not author or len(author) < 3:
            continue
        
        liked_title = book_title.get(liked_bid, str(liked_bid))
        
        for rec_title in recs[:10]:
            for bid in book_title:
                if book_title[bid] == rec_title:
                    rec_author = book_author.get(bid, '').split(',')[0].strip()
                    if rec_author == author and bid not in u_liked:
                        matches.append((author, liked_title[:35], rec_title[:35], recs.index(rec_title) + 1))
                    break
    
    if matches:
        print(f'{un}:')
        for auth, liked_t, rec_t, rank in matches[:3]:
            print(f'  Read "{liked_t}" by {auth} -> Recommended "{rec_t}" (rank {rank})')
        print()
