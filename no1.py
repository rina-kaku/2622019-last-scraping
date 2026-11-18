import re
import sqlite3
import time
import requests
from bs4 import BeautifulSoup

DB_NAME = "google_repos.db"
BASE_URL = "https://github.com/orgs/google/repositories"
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "en-US,en;q=0.9",
}


def parse_stars(star_text: str) -> int:
    """'1.2k' や '12,345' などのスター表記を整数に変換する"""
    text = star_text.strip().lower().replace(",", "")
    if not text:
        return 0
    try:
        if text.endswith("k"):
            return int(float(text[:-1]) * 1000)
        if text.endswith("m"):
            return int(float(text[:-1]) * 1_000_000)
        return int(text)
    except ValueError:
        return 0


def scrape_all_repositories() -> list[tuple[str, str, int]]:
    """Googleの全リポジトリをスクレイピングして (リポジトリ名, 主要な言語, スター数) のリストを返す"""
    all_repos = []
    seen_names = set()
    page = 1

    session = requests.Session()
    session.headers.update(HEADERS)

    while True:
        url = f"{BASE_URL}?page={page}"
        print(f"取得中: {url}")

        response = session.get(url, timeout=15)
        if response.status_code != 200:
            print(f"ステータスコード {response.status_code} のため終了します。")
            break

        soup = BeautifulSoup(response.text, "html.parser")

        # GitHubのHTML構造に合わせてリポジトリ行を取得（新UI・旧UI両対応）
        repo_items = soup.select("div[data-testid='list-view-item'], li.Box-row, li[itemprop='owns']")
        if not repo_items:
            # フォールバック: /google/<repo_name> への見出しリンクから親要素を辿る
            repo_links = soup.select("h3 a[href^='/google/'], h4 a[href^='/google/']")
            repo_items = [link.find_parent(["li", "div"]) for link in repo_links if link.find_parent(["li", "div"])]

        if not repo_items:
            print("これ以上リポジトリが見つからないため終了します。")
            break

        added_in_page = 0
        for item in repo_items:
            # 1. リポジトリ名の取得
            name_tag = (
                item.find("a", itemprop="name codeRepository")
                or item.select_one("h3 a[href^='/google/'], h4 a[href^='/google/']")
            )
            if not name_tag:
                continue

            name = name_tag.get_text(strip=True)
            if not name or name in seen_names:
                continue
            seen_names.add(name)

            # 2. 主要な言語の取得
            lang_tag = item.find("span", itemprop="programmingLanguage")
            if not lang_tag:
                # 新UI向け: 言語色ドット(span)の隣にあるテキストを探す
                lang_color = item.select_one("span[class*='repo-language-color'], span[style*='background-color']")
                if lang_color and lang_color.parent:
                    lang_text = lang_color.parent.get_text(strip=True)
                    language = lang_text if lang_text else "None"
                else:
                    language = "None"
            else:
                language = lang_tag.get_text(strip=True)

            # 3. スター数の取得
            star_tag = item.find("a", href=re.compile(r"/stargazers$"))
            if not star_tag:
                star_tag = item.select_one("a[aria-label*='star' i], span[aria-label*='star' i]")
            stars = parse_stars(star_tag.get_text(strip=True)) if star_tag else 0

            all_repos.append((name, language, stars))
            added_in_page += 1

        if added_in_page == 0:
            print("新規リポジトリが0件のため終了します。")
            break

        page += 1
        # 課題要件: 必ず1秒待機する
        time.sleep(1)

    return all_repos


def save_to_db(repos: list[tuple[str, str, int]]) -> None:
    """SQLiteデータベースを作成し、スクレイピングしたデータを保存する"""
    with sqlite3.connect(DB_NAME) as conn:
        cursor = conn.cursor()

        # 再実行時の重複を防ぐためテーブルを再作成
        cursor.execute("DROP TABLE IF EXISTS repositories")
        cursor.execute(
            """
            CREATE TABLE repositories (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL UNIQUE,
                language TEXT,
                stars INTEGER NOT NULL
            )
            """
        )

        cursor.executemany(
            "INSERT INTO repositories (name, language, stars) VALUES (?, ?, ?)",
            repos,
        )
        conn.commit()
    print(f"\nデータベース ({DB_NAME}) に {len(repos)} 件保存しました。")


def display_from_db() -> None:
    """保存したデータをSELECT文で取得して表示する"""
    with sqlite3.connect(DB_NAME) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT id, name, language, stars FROM repositories ORDER BY stars DESC")
        rows = cursor.fetchall()

    print(f"\n--- SELECT文の実行結果（全 {len(rows)} 件 / スター数順） ---")
    for row in rows:
        print(f"ID: {row[0]:4d} | リポジトリ名: {row[1]:35s} | 主要言語: {row[2]:15s} | スター数: {row[3]}")


if __name__ == "__main__":
    repositories = scrape_all_repositories()
    save_to_db(repositories)
    display_from_db()