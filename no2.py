import sqlite3
import time
import requests
from bs4 import BeautifulSoup

# 1. SQLiteデータベースとテーブルの作成
db_name = "google_repos.db"
conn = sqlite3.connect(db_name)
cursor = conn.cursor()

cursor.execute("DROP TABLE IF EXISTS repositories")
cursor.execute("""
    CREATE TABLE repositories (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL,
        language TEXT,
        stars TEXT
    )
""")
conn.commit()

# 2. スクレイピング処理
base_url = "https://github.com/orgs/google/repositories"
headers = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
}

page = 1
total_saved = 0

while True:
    url = f"{base_url}?page={page}"
    print(f"Fetching: {url}")
    
    response = requests.get(url, headers=headers)
    if response.status_code != 200:
        print(f"ページの取得に失敗しました (Status: {response.status_code})")
        break

    soup = BeautifulSoup(response.text, "html.parser")
    repo_items = soup.select("li.Box-row, div[data-testid='results-list'] > div, ul[data-listview-component='items-list'] > li")
    
    if not repo_items:
        print("すべてのページを取得しました。")
        break

    page_data = []
    for item in repo_items:
        # リポジトリ名の取得
        name_tag = item.select_one("a[itemprop='name codeRepository'], h3 a, a[data-testid='listitem-title-link']")
        if not name_tag:
            continue
        repo_name = name_tag.get_text(strip=True)

        # 主要な言語の取得（複数のHTMLパターンに対応）
        language = "None"
        lang_tag = item.select_one("span[itemprop='programmingLanguage'], span[data-testid='listitem-language']")
        
        if lang_tag:
            language = lang_tag.get_text(strip=True)
        else:
            # パターンB: 言語の色丸（repo-language-color 等）の直後にある span を探す
            color_dot = item.select_one("span.repo-language-color, span[class*='language-color'], span[style*='background-color']")
            if color_dot and color_dot.find_next_sibling("span"):
                language = color_dot.find_next_sibling("span").get_text(strip=True)
            else:
                # パターンC: メタ情報エリア内の言語表示（ライセンスやスター数の左側にあるテキスト）
                # 言語アイコン(svg)の隣、または特定のクラスを持つspanを探索
                for span in item.select("div span"):
                    text = span.get_text(strip=True)
                    # 代表的な言語名や、スター数・日時・ライセンス以外の短いテキストを判定
                    if span.find_previous_sibling("span") and "background-color" in str(span.find_previous_sibling("span")):
                        language = text
                        break

        # スター数の取得
        star_tag = item.select_one("a[href$='/stargazers'], span[data-testid='listitem-stars']")
        stars = star_tag.get_text(strip=True) if star_tag else "0"

        page_data.append((repo_name, language, stars))

    if not page_data:
        break

    # 3. データベースへ保存
    cursor.executemany(
        "INSERT INTO repositories (name, language, stars) VALUES (?, ?, ?)",
        page_data
    )
    conn.commit()
    
    total_saved += len(page_data)
    print(f"Page {page}: {len(page_data)} 件保存しました（累計: {total_saved} 件）")

    page += 1
    time.sleep(1)

# 4. 保存したデータをSELECT文で表示
print("\n--- 保存されたデータ（先頭20件を表示） ---")
cursor.execute("SELECT id, name, language, stars FROM repositories LIMIT 20")
rows = cursor.fetchall()

for row in rows:
    print(f"ID: {row[0]} | リポジトリ名: {row[1]} | 言語: {row[2]} | スター数: {row[3]}")

conn.close()