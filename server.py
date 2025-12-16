# server.py
# Webスクレイピング用MCPサーバー

import logging
import asyncio
import json
import os
import re
from pathlib import Path
from urllib.parse import urljoin, urlparse
from typing import Any, Dict, List, Optional, Tuple
from bs4 import BeautifulSoup
from bs4.element import Tag
from mcp.server.fastmcp import FastMCP
import aiohttp
from aiohttp import ClientTimeout, BasicAuth

# Playwrightのインポート
try:
    from playwright.async_api import async_playwright
    PLAYWRIGHT_AVAILABLE = True
except ImportError:
    async_playwright = None
    PLAYWRIGHT_AVAILABLE = False

# Google Sheets APIのインポート
try:
    from google.oauth2 import service_account
    from googleapiclient.discovery import build
    from googleapiclient.errors import HttpError
    GOOGLE_SHEETS_AVAILABLE = True
except ImportError:
    service_account = None
    build = None
    HttpError = None
    GOOGLE_SHEETS_AVAILABLE = False

# ログファイルのパスを動的に決定（スクリプトのディレクトリに保存）
_log_dir = Path(__file__).parent
_log_file = _log_dir / 'debug.log'
# ディレクトリが存在しない場合は作成
_log_dir.mkdir(parents=True, exist_ok=True)

# ログ設定
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(str(_log_file)),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# ブラウザ数制限
MAX_BROWSERS = 5
browser_semaphore = asyncio.Semaphore(MAX_BROWSERS)

CLOUD_GYM_BASE_URL = "https://cloud-gym.com/personal-fitness"
CLOUD_GYM_POST_TYPE = "introduce"
CLOUD_GYM_API_ENDPOINT = f"{CLOUD_GYM_BASE_URL.rstrip('/')}/wp-json/wp/v2/{CLOUD_GYM_POST_TYPE}"
CLOUD_GYM_DEFAULT_FIELDS = "id,title,excerpt,date,link,slug"

# Rakuraku Media School settings
RAKURAKU_SITE_URL = "https://rakuraku.app/media/school"
RAKURAKU_POST_TYPE = "school-list"
RAKURAKU_API_BASE = f"{RAKURAKU_SITE_URL.rstrip('/')}/wp-json/wp/v2"
RAKURAKU_DEFAULT_FIELDS = "id,title,slug,date,link,status"
RAKURAKU_WP_USERNAME = "rakuraku-admin-school"
RAKURAKU_WP_APP_PASSWORD = "ajBN QdvS fPGS 0L9O SkeV CgVJ"
RAKURAKU_FIELD_CONTAINERS = {"custom_fields", "meta", "acf"}
RAKURAKU_ALLOWED_STATUSES = ["publish", "draft"]


def _rakuraku_credentials_ready() -> bool:
    return bool(RAKURAKU_WP_USERNAME and RAKURAKU_WP_APP_PASSWORD)


def _rakuraku_missing_credentials_message() -> str:
    return (
        "Rakuraku Media School のWordPress APIにアクセスするには、"
        "環境変数 RAKURAKU_WP_USERNAME と RAKURAKU_WP_APP_PASSWORD を設定してください。"
    )


def _wp_extract_text(field: Any) -> str:
    if isinstance(field, dict):
        return field.get("rendered") or field.get("raw") or ""
    if isinstance(field, list):
        return ", ".join(str(item) for item in field if item not in (None, ""))
    if field is None:
        return ""
    return str(field)


def _flatten_field_value(value: Any) -> Any:
    if isinstance(value, list):
        if len(value) == 1:
            return _flatten_field_value(value[0])
        return [_flatten_field_value(v) for v in value]
    if isinstance(value, dict):
        return {k: _flatten_field_value(v) for k, v in value.items()}
    return value


def _rakuraku_collect_custom_fields(post: Dict[str, Any]) -> Dict[str, Any]:
    fields: Dict[str, Any] = {}
    for key in ("custom_fields", "meta", "acf"):
        raw = post.get(key)
        if isinstance(raw, dict):
            for f_key, f_val in raw.items():
                fields[f_key] = _flatten_field_value(f_val)
    return fields


def _truncate_value(value: Any, limit: int = 120) -> str:
    text = _wp_extract_text(value) if isinstance(value, dict) else str(value)
    text = text.strip()
    if len(text) > limit:
        return text[: limit - 3] + "..."
    return text


def _strip_html(html: str) -> str:
    try:
        soup = BeautifulSoup(html, "html.parser")
        return soup.get_text(separator=" ", strip=True)
    except Exception:
        return html


def _rakuraku_format_summary(post: Dict[str, Any], include_fields: bool = False) -> str:
    title = _wp_extract_text(post.get("title"))
    link = post.get("link", "")
    post_id = post.get("id")
    slug = post.get("slug", "")
    status = post.get("status", "")
    date_str = post.get("date", "")
    
    summary = [
        "━━━━━━━━━━━━━━━━━━━━",
        f"📍 {title or 'タイトル未設定'}",
        f"🆔 ID: {post_id} / slug: {slug}",
        f"📅 公開日: {date_str or 'N/A'} / status: {status or '不明'}",
        f"🔗 {link or 'リンクなし'}",
    ]
    
    if include_fields:
        fields = _rakuraku_collect_custom_fields(post)
        if fields:
            preview_items = []
            for key, value in list(fields.items())[:6]:
                preview_items.append(f"{key}={_truncate_value(value, 60)}")
            if preview_items:
                summary.append("🔧 カスタムフィールド:")
                summary.append("   " + ", ".join(preview_items))
    
    return "\n".join(summary)


def _rakuraku_format_detail(post: Dict[str, Any]) -> str:
    title = _wp_extract_text(post.get("title"))
    summary = [
        "━━━━━━━━━━━━━━━━━━━━",
        f"📍 {title or 'タイトル未設定'}",
        f"🆔 ID: {post.get('id')} / slug: {post.get('slug')}",
        f"📅 公開日: {post.get('date')} / 最終更新: {post.get('modified')}",
        f"👤 author: {post.get('author')}",
        f"🔗 {post.get('link')}",
        "━━━━━━━━━━━━━━━━━━━━",
    ]
    
    content = post.get("content", {}).get("rendered")
    if content:
        stripped = _strip_html(content)
        summary.append("📝 本文（冒頭200文字）:")
        summary.append(_truncate_value(stripped, 200))
    
    excerpt = post.get("excerpt", {}).get("rendered")
    if excerpt:
        summary.append("\n💡 抜粋:")
        summary.append(_truncate_value(_strip_html(excerpt), 160))
    
    fields = _rakuraku_collect_custom_fields(post)
    if fields:
        summary.append("\n🔧 カスタムフィールド一覧:")
        for key, value in fields.items():
            summary.append(f"- {key}: {_truncate_value(value)}")
    else:
        summary.append("\n🔧 カスタムフィールドは見つかりませんでした。")
    
    return "\n".join(summary)


async def _rakuraku_wp_get(path: str, params: Optional[Dict[str, Any]] = None) -> Tuple[Any, Dict[str, str]]:
    if not _rakuraku_credentials_ready():
        raise RuntimeError(_rakuraku_missing_credentials_message())
    
    url = path
    if not url.startswith("http"):
        url = f"{RAKURAKU_API_BASE.rstrip('/')}/{path.lstrip('/')}"
    
    auth = BasicAuth(RAKURAKU_WP_USERNAME, RAKURAKU_WP_APP_PASSWORD)
    timeout = ClientTimeout(total=30)
    
    async with aiohttp.ClientSession(timeout=timeout) as session:
        async with session.get(url, params=params, auth=auth) as response:
            try:
                payload = await response.json(content_type=None)
            except Exception:
                payload = await response.text()
            
            if response.status >= 400:
                error_details = payload if isinstance(payload, dict) else {"message": str(payload)}
                raise RuntimeError(
                    f"WordPress APIエラー (HTTP {response.status}): {json.dumps(error_details, ensure_ascii=False)}"
                )
            
            headers = {k: v for k, v in response.headers.items()}
            return payload, headers


async def _rakuraku_find_post(identifier: str) -> Optional[Dict[str, Any]]:
    params = {"context": "edit", "status": ",".join(RAKURAKU_ALLOWED_STATUSES)}
    
    if identifier.isdigit():
        path = f"{RAKURAKU_POST_TYPE}/{identifier}"
        post, _ = await _rakuraku_wp_get(path, params=params)
        if isinstance(post, dict):
            return post
        return None
    
    # slug or title search
    slug_params = params | {"slug": identifier, "per_page": 1}
    posts, _ = await _rakuraku_wp_get(RAKURAKU_POST_TYPE, params=slug_params)
    if isinstance(posts, list) and posts:
        return posts[0]
    
    search_params = params | {"search": identifier, "per_page": 1}
    posts, _ = await _rakuraku_wp_get(RAKURAKU_POST_TYPE, params=search_params)
    if isinstance(posts, list) and posts:
        return posts[0]
    
    return None


async def _rakuraku_wp_post(path: str, payload: Dict[str, Any]) -> Dict[str, Any]:
    if not _rakuraku_credentials_ready():
        raise RuntimeError(_rakuraku_missing_credentials_message())
    
    url = path
    if not url.startswith("http"):
        url = f"{RAKURAKU_API_BASE.rstrip('/')}/{path.lstrip('/')}"
    
    auth = BasicAuth(RAKURAKU_WP_USERNAME, RAKURAKU_WP_APP_PASSWORD)
    timeout = ClientTimeout(total=30)
    
    async with aiohttp.ClientSession(timeout=timeout) as session:
        async with session.post(url, json=payload, auth=auth) as response:
            try:
                payload_resp = await response.json(content_type=None)
            except Exception:
                payload_resp = await response.text()
            
            if response.status >= 400:
                error_details = payload_resp if isinstance(payload_resp, dict) else {"message": str(payload_resp)}
                raise RuntimeError(
                    f"WordPress APIエラー (HTTP {response.status}): {json.dumps(error_details, ensure_ascii=False)}"
                )
            if isinstance(payload_resp, dict):
                return payload_resp
            raise RuntimeError("予期しないレスポンス形式です。JSONオブジェクトを受信できませんでした。")


def _rakuraku_format_update_summary(
    post: Dict[str, Any],
    updated_fields: Dict[str, Any],
    field_group: str
) -> str:
    title = _wp_extract_text(post.get("title"))
    lines = [
        "✅ 更新成功",
        f"ID: {post.get('id')} / slug: {post.get('slug')}",
        f"タイトル: {title or '(タイトル未設定)'}",
        f"対象: {field_group}",
        "",
        "更新内容:"
    ]
    for key, value in updated_fields.items():
        lines.append(f"  • {key}: {value}")
    return "\n".join(lines)


def _rakuraku_build_status_param(arg: Optional[str]) -> str:
    tokens: List[str] = []
    if arg:
        tokens = [token.strip().lower() for token in arg.split(",") if token.strip()]
    selected = [token for token in tokens if token in RAKURAKU_ALLOWED_STATUSES]
    if not selected:
        selected = RAKURAKU_ALLOWED_STATUSES.copy()
    ordered_unique: List[str] = []
    for status in selected:
        if status not in ordered_unique:
            ordered_unique.append(status)
    return ",".join(ordered_unique)


def _rakuraku_normalize_single_status(status: Optional[str]) -> str:
    value = (status or "").strip().lower()
    if value in RAKURAKU_ALLOWED_STATUSES:
        return value
    return "draft"


def _rakuraku_parse_fields_json(raw: str) -> Tuple[Optional[Dict[str, Any]], Optional[str]]:
    if not raw or not raw.strip():
        return None, None
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        return None, f"❌ JSONの形式が正しくありません: {exc}"
    if not isinstance(data, dict):
        return None, "❌ JSONはオブジェクト（Key/Value形式）で指定してください。"
    return data, None


def _rakuraku_build_edit_url(post_id: Any) -> str:
    try:
        pid = int(post_id)
    except Exception:
        pid = post_id
    return f"{RAKURAKU_SITE_URL.rstrip('/')}/wp-admin/post.php?post={pid}&action=edit"


def _rakuraku_format_post_action_result(action: str, post: Dict[str, Any]) -> str:
    title = _wp_extract_text(post.get("title")) or "(タイトル未設定)"
    status = post.get("status", "unknown")
    post_id = post.get("id")
    link = post.get("link") or ""
    edit_url = _rakuraku_build_edit_url(post_id) if post_id else "N/A"
    lines = [
        action,
        f"🆔 ID: {post_id} / status: {status}",
        f"📍 タイトル: {title}",
        f"🔗 表示URL: {link or 'N/A'}",
        f"✏️ 編集URL: {edit_url}",
    ]
    return "\n".join(lines)


async def _rakuraku_handle_update_tool(
    *,
    post_type: str,
    post_id: int,
    fields_json: str,
    container: str,
    wrap_payload: bool,
    label: str
) -> str:
    try:
        data = json.loads(fields_json)
    except json.JSONDecodeError as exc:
        return (
            "❌ JSONの形式に問題があります。\n"
            f"エラー: {exc}\n"
            "例: {\"カスタムフィールド名\": \"値\"}"
        )
    
    if not isinstance(data, dict) or not data:
        return "❌ JSONはキーと値を持つオブジェクト形式で指定してください。"
    
    container = (container or "custom_fields").strip()
    wrap_payload = bool(wrap_payload)
    
    if wrap_payload:
        if container not in RAKURAKU_FIELD_CONTAINERS:
            return (
                f"❌ container='{container}' はサポートされていません。"
                " 使用可能: custom_fields / meta / acf"
            )
        payload = {container: data}
        summary_fields = data
        field_group = f"{label}:{container}"
    else:
        payload = data
        summary_fields = data
        field_group = f"{label}:raw"
    
    logger.info(
        "[Rakuraku] 更新開始 post_type=%s id=%s container=%s wrap=%s",
        post_type,
        post_id,
        container,
        wrap_payload,
    )
    
    try:
        post = await _rakuraku_wp_post(f"{post_type}/{post_id}", payload)
    except RuntimeError as exc:
        logger.error(
            "[Rakuraku] 更新失敗 post_type=%s id=%s : %s",
            post_type,
            post_id,
            exc,
        )
        return f"❌ 更新に失敗しました。\n{exc}"
    
    return _rakuraku_format_update_summary(post, summary_fields, field_group)

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# MCPサーバー作成
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
mcp = FastMCP("web-scraping-server")

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# ツール定義
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

@mcp.tool()
async def fetch_page_content(url: str) -> str:
    """
    指定URLのページコンテンツを取得し、メイン部分のテキストを抽出します。
    通常のHTMLページに最適です。
    
    Args:
        url: 取得対象のURL（例：「https://example.com/page」）
    
    Returns:
        ページのメインコンテンツのテキスト（JSON形式）
    """
    logger.info(f"fetch_page_content called with url={url}")
    
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/120.0.0.0 Safari/537.36"
        ),
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
        "Accept-Language": "ja,en-US;q=0.7,en;q=0.3",
        "Accept-Encoding": "gzip, deflate",
        "DNT": "1",
        "Connection": "keep-alive",
        "Upgrade-Insecure-Requests": "1",
        "Sec-Fetch-Dest": "document",
        "Sec-Fetch-Mode": "navigate",
        "Sec-Fetch-Site": "none",
        "Cache-Control": "max-age=0"
    }
    
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url, headers=headers, timeout=ClientTimeout(total=20)) as response:
                if response.status != 200:
                    error_msg = f"Failed to fetch page: {response.status}"
                    logger.error(error_msg)
                    return f"エラー: {error_msg}\nURL: {url}"
                
                html = await response.text()
                soup = BeautifulSoup(html, "html.parser")
                
                # 不要なタグを除去
                for tag in soup(["script", "style", "noscript", "header", "footer", "nav"]):
                    tag.decompose()
                
                # メインコンテンツを探す（優先順位付き）
                main_content = None
                
                # 1. main タグ
                main_content = soup.find("main")
                
                # 2. article タグ
                if not main_content:
                    main_content = soup.find("article")
                
                # 3. role="main" 属性
                if not main_content:
                    main_content = soup.find(attrs={"role": "main"})
                
                # 4. id or class に content/main が含まれる要素
                if not main_content:
                    for selector in ["#content", ".content", "#main", ".main", 
                                   "[id*='content']", "[class*='content']"]:
                        main_content = soup.select_one(selector)
                        if main_content:
                            break
                
                # 5. body全体をフォールバック
                if not main_content:
                    main_content = soup.find("body")
                
                # テキスト抽出
                if main_content:
                    # 改行やタブを正規化
                    text = main_content.get_text(separator="\n", strip=True)
                    # 連続する空白行を削除
                    lines = [line.strip() for line in text.split('\n') if line.strip()]
                    content = '\n'.join(lines)
                else:
                    content = ""
                
                # ページタイトルも取得（参考情報として）
                title = ""
                title_tag = soup.find("title")
                if title_tag:
                    title = title_tag.get_text(strip=True)
                
                logger.info(f"Successfully extracted content: {len(content)} chars")
                
                # 結果を整形して返す
                result = f"━━━━━━━━━━━━━━━━━━━━\n"
                result += f"📄 {title}\n"
                result += f"━━━━━━━━━━━━━━━━━━━━\n\n"
                result += f"🔗 URL: {url}\n"
                result += f"📝 コンテンツ長: {len(content)} 文字\n\n"
                result += f"【抽出されたコンテンツ】\n\n"
                result += content
                
                return result
                
    except Exception as e:
        logger.exception(f"Error in fetch_page_content: {e}")
        return f"エラーが発生しました: {str(e)}\nURL: {url}"


@mcp.tool()
async def fetch_page_content_with_playwright(url: str) -> str:
    """
    Playwrightを使用してJavaScript/SPA/Reactサイトのページコンテンツを取得します。
    動的にレンダリングされるページに最適です。
    Shadow DOMやカスタム要素にも対応しています。
    
    Args:
        url: 取得対象のURL（例：「https://example.com/spa-page」）
    
    Returns:
        ページのメインコンテンツのテキスト（JSON形式）
    """
    logger.info(f"fetch_page_content_with_playwright called with url={url}")
    
    if not PLAYWRIGHT_AVAILABLE:
        error_msg = "Playwright is not available. Please install it with: pip install playwright && playwright install"
        logger.error(error_msg)
        return f"エラー: {error_msg}"
    
    if not async_playwright:
        return "エラー: Playwright not available"
    
    # PDFを事前に除外
    if url.lower().endswith('.pdf'):
        logger.warning(f"Skipping PDF: {url}")
        return f"エラー: PDFファイルはサポートされていません\nURL: {url}"
    
    async with browser_semaphore:  # ブラウザ数制限
        browser = None
        context = None
        page = None
        try:
            logger.debug(f"Starting Playwright extraction for: {url}")
            async with async_playwright() as p:
                # ブラウザを起動
                browser = await p.chromium.launch(
                    headless=True,
                    args=['--no-sandbox', '--single-process']
                )
                # Contextを作成
                context = await browser.new_context(
                    viewport={'width': 1920, 'height': 1080}
                )
                page = await context.new_page()
                
                # User-Agentを設定
                await page.set_extra_http_headers({
                    "User-Agent": (
                        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                        "AppleWebKit/537.36 (KHTML, like Gecko) "
                        "Chrome/120.0.0.0 Safari/537.36"
                    ),
                    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
                    "Accept-Language": "ja,en-US;q=0.7,en;q=0.3",
                })
                
                # ページにアクセス
                logger.debug(f"Navigating to {url}")
                await page.goto(url, wait_until="domcontentloaded", timeout=15000)
                
                # ネットワークが落ち着くまで待機
                await page.wait_for_load_state("networkidle")
                
                # プライバシー同意ダイアログの処理
                try:
                    consent_selectors = [
                        "#accept",
                        ".accept.uc-accept-button",
                        "[data-action='consent'][data-action-type='accept']",
                        "button:has-text('すべて受け入れる')",
                        "button:has-text('同意')",
                        "button:has-text('Accept')",
                        "button:has-text('OK')",
                    ]
                    
                    for selector in consent_selectors:
                        try:
                            if await page.locator(selector).count() > 0:
                                await page.click(selector, timeout=2000)
                                await page.wait_for_timeout(1000)
                                break
                        except:
                            continue
                except:
                    pass
                
                # コンテンツが表示されるのを待つ
                try:
                    await page.wait_for_selector(
                        "main, article, [role='main'], .content, #content, .main-content",
                        timeout=10000
                    )
                except:
                    logger.warning("No main content selector found, continuing...")
                
                # SPAのレンダリング完了を待つ
                await page.wait_for_timeout(5000)
                
                # JavaScriptで直接コンテンツを取得（Shadow DOM対応）
                content_data = await page.evaluate("""
                    () => {
                        // Shadow DOMも含めてテキストを取得する関数
                        function extractAllText(element) {
                            let text = '';
                            
                            // Shadow rootがある場合
                            if (element.shadowRoot) {
                                const shadowElements = element.shadowRoot.querySelectorAll('*');
                                shadowElements.forEach(el => {
                                    text += extractAllText(el) + ' ';
                                });
                            }
                            
                            // 通常のDOM要素の処理
                            if (element.nodeType === Node.TEXT_NODE) {
                                text += element.textContent || '';
                            } else if (element.nodeType === Node.ELEMENT_NODE) {
                                // スクリプトやスタイル、メタデータは除外
                                if (!['SCRIPT', 'STYLE', 'NOSCRIPT', 'META', 'LINK'].includes(element.tagName)) {
                                    for (const child of element.childNodes) {
                                        text += extractAllText(child) + ' ';
                                    }
                                }
                            }
                            
                            return text;
                        }
                        
                        // 事前にscriptとstyleを全て削除
                        document.querySelectorAll('script, style, noscript').forEach(el => el.remove());
                        
                        // メインコンテンツを探す
                        const selectors = [
                            'main',
                            'article',
                            '[role="main"]',
                            '#content',
                            '.content',
                            '#main',
                            '.main',
                            '.main-content',
                            '.page-content',
                            'body'
                        ];
                        
                        let mainContent = null;
                        for (const selector of selectors) {
                            mainContent = document.querySelector(selector);
                            if (mainContent) break;
                        }
                        
                        // ヘッダー、フッター、ナビゲーションを除外
                        if (mainContent) {
                            const excludeSelectors = ['header', 'footer', 'nav', '.header', '.footer', '.navigation'];
                            excludeSelectors.forEach(selector => {
                                const elements = mainContent.querySelectorAll(selector);
                                elements.forEach(el => el.remove());
                            });
                            
                            mainContent.querySelectorAll('script, style, noscript').forEach(el => el.remove());
                        }
                        
                        // Shadow DOMも含めた全テキスト取得
                        const shadowDomText = mainContent ? extractAllText(mainContent) : '';
                        const innerText = mainContent ? mainContent.innerText : '';
                        const textContent = mainContent ? mainContent.textContent : '';
                        
                        // タイトルも取得
                        const title = document.title || '';
                        
                        return {
                            title: title,
                            shadowDomText: shadowDomText.trim(),
                            innerText: innerText.trim(),
                            textContent: textContent.trim(),
                            shadowDomLength: shadowDomText.length,
                            innerTextLength: innerText.length,
                            textContentLength: textContent.length
                        };
                    }
                """)
                
                # mailto: と tel: のリンクを抽出
                try:
                    link_hrefs = await page.evaluate("""
                        () => Array.from(document.querySelectorAll('a[href^="mailto:"], a[href^="tel:"]'))
                            .map(a => a.getAttribute('href') || '')
                    """)
                except Exception:
                    link_hrefs = []
                
                # 最適なコンテンツを選択
                content = ""
                
                # Nuxt.js/Vue.jsのJSONデータをフィルタリング
                def is_json_data(text):
                    if not text:
                        return False
                    json_patterns = ['window.__NUXT__', '["[\"Reactive\"', '{"data":', 'googleapis.com']
                    return any(pattern in text[:500] for pattern in json_patterns)
                
                if content_data.get('innerText') and len(content_data['innerText']) > 100 and not is_json_data(content_data['innerText']):
                    content = content_data['innerText']
                    logger.debug(f"Using innerText: {len(content)} chars")
                elif content_data.get('shadowDomText') and len(content_data['shadowDomText']) > 100 and not is_json_data(content_data['shadowDomText']):
                    content = content_data['shadowDomText']
                    logger.debug(f"Using shadowDomText: {len(content)} chars")
                elif content_data.get('textContent') and not is_json_data(content_data['textContent']):
                    content = content_data['textContent']
                    logger.debug(f"Using textContent: {len(content)} chars")
                else:
                    content = ""
                    logger.warning("No valid content found (JSON data detected)")
                
                # テキストの正規化
                if content:
                    content = ' '.join(content.split())
                    lines = content.split('.')
                    content = '.\n'.join(line.strip() for line in lines if line.strip())
                
                # 抽出したメール・電話番号を整形
                extracted_emails = []
                extracted_phones = []
                try:
                    for href in link_hrefs:
                        h = (href or '').strip()
                        if h.lower().startswith('mailto:'):
                            email = h.split(':', 1)[1].split('?', 1)[0]
                            if email:
                                extracted_emails.append(email)
                        elif h.lower().startswith('tel:'):
                            number = h.split(':', 1)[1]
                            if number:
                                extracted_phones.append(number)
                except Exception:
                    pass
                
                logger.info(f"Successfully extracted content: {len(content)} chars")
                
                # 結果を整形して返す
                result = f"━━━━━━━━━━━━━━━━━━━━\n"
                result += f"📄 {content_data.get('title', '')}\n"
                result += f"━━━━━━━━━━━━━━━━━━━━\n\n"
                result += f"🔗 URL: {url}\n"
                result += f"📝 コンテンツ長: {len(content)} 文字\n"
                result += f"🔧 抽出方法: Playwright (JavaScript rendering)\n"
                
                if extracted_emails:
                    result += f"📧 メールアドレス: {', '.join(set(extracted_emails))}\n"
                if extracted_phones:
                    result += f"📞 電話番号: {', '.join(set(extracted_phones))}\n"
                
                result += f"\n【抽出されたコンテンツ】\n\n"
                result += content
                
                if len(content) < 100:
                    result += "\n\n⚠️ 警告: コンテンツが少ない可能性があります。認証が必要なページか、動的読み込みに時間がかかるページかもしれません。"
                
                return result
                
        except Exception as e:
            logger.exception(f"Error in fetch_page_content_with_playwright: {e}")
            return f"エラーが発生しました: {str(e)}\nURL: {url}"
        finally:
            # 完全な終了処理
            try:
                if page:
                    await page.close()
            except:
                pass
            try:
                if context:
                    await context.close()
            except:
                pass
            try:
                if browser:
                    await browser.close()
                    await asyncio.sleep(1)
            except:
                pass


@mcp.tool()
async def extract_site_links(url: str) -> str:
    """
    公式サイトからheader/footer/navのリンクを抽出し、仮想サイトマップを作成します。
    通常のHTMLページに最適です。
    
    Args:
        url: 対象サイトのURL（例：「https://www.goldsgym.jp」）
    
    Returns:
        サイトのリンク情報のJSON文字列。各リンクにはtext, url、content_headings(見出しリスト)が含まれる
    """
    logger.info(f"extract_site_links called with url={url}")
    
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/120.0.0.0 Safari/537.36"
        ),
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
        "Accept-Language": "ja,en-US;q=0.7,en;q=0.3",
        "Accept-Encoding": "gzip, deflate",
        "DNT": "1",
        "Connection": "keep-alive",
        "Upgrade-Insecure-Requests": "1",
        "Sec-Fetch-Dest": "document",
        "Sec-Fetch-Mode": "navigate",
        "Sec-Fetch-Site": "none",
        "Cache-Control": "max-age=0"
    }
    
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url, headers=headers, timeout=ClientTimeout(total=20)) as response:
                if response.status != 200:
                    error_msg = f"Failed to fetch page: {response.status}"
                    logger.error(error_msg)
                    return json.dumps({
                        "error": error_msg,
                        "base_url": url,
                        "links": []
                    }, ensure_ascii=False)
                
                html = await response.text()
                soup = BeautifulSoup(html, "html.parser")
                
                # スクリプトとスタイルを除去
                for tag in soup(["script", "style", "noscript"]):
                    tag.decompose()
                
                # header/footer/nav要素を探す
                header = soup.find("header") or soup.select_one('[role="banner"]')
                footer = soup.find("footer") or soup.select_one('[role="contentinfo"]')
                
                # 独立したnav要素を探す（headerの外にあるもの）
                nav_elements = soup.find_all("nav")
                independent_navs = []
                if header and isinstance(header, Tag):
                    header_navs = header.find_all("nav")
                    independent_navs = [nav for nav in nav_elements if nav not in header_navs]
                else:
                    independent_navs = nav_elements
                
                # リンクを抽出する内部関数
                def extract_links_from_element(element):
                    if element is None:
                        return []
                    
                    links = []
                    for link in element.find_all('a', href=True):
                        text = link.get_text(strip=True)
                        href = link['href']
                        
                        # 相対URLを絶対URLに変換
                        absolute_url = urljoin(url, href)
                        
                        # テキストが空でない場合のみ処理
                        if text:
                            links.append({
                                'text': text,
                                'url': absolute_url
                            })
                    return links
                
                # 各セクションからリンクを抽出
                header_links = extract_links_from_element(header)
                footer_links = extract_links_from_element(footer)
                nav_links = []
                for nav in independent_navs:
                    nav_links.extend(extract_links_from_element(nav))
                
                # パターン検出と除去
                def extract_url_pattern(url: str, base_url: str = "") -> str:
                    """URLからパーマリンク構造のパターンを抽出（ベースURLを考慮）"""
                    try:
                        parsed = urlparse(url)
                        base_parsed = urlparse(base_url)
                        
                        # ベースURLのパス部分を除外
                        base_path = base_parsed.path.strip('/')
                        full_path = parsed.path.strip('/')
                        
                        # ベースURLのパスが含まれている場合、それを除外
                        if base_path and full_path.startswith(base_path):
                            relative_path = full_path[len(base_path):].strip('/')
                        else:
                            relative_path = full_path
                        
                        if relative_path:
                            parts = relative_path.split('/')
                            if len(parts) >= 2:
                                pattern_parts = parts[:-1] + ['*']
                                return '/' + '/'.join(pattern_parts) + '/'
                        
                        return parsed.path
                    except:
                        return url
                
                def detect_repeated_patterns(all_links: list, threshold: int = 10, base_url: str = "") -> set:
                    """同じパーマリンク構造が閾値回数以上繰り返されるパターンを検出（ベースURLを考慮）"""
                    pattern_counts = {}
                    url_to_pattern = {}
                    
                    for link in all_links:
                        url = link['url']
                        pattern = extract_url_pattern(url, base_url)
                        
                        pattern_counts[pattern] = pattern_counts.get(pattern, 0) + 1
                        url_to_pattern[url] = pattern
                    
                    repeated_patterns = {pattern for pattern, count in pattern_counts.items() 
                                       if count >= threshold}
                    
                    urls_to_exclude = set()
                    for url, pattern in url_to_pattern.items():
                        if pattern in repeated_patterns:
                            urls_to_exclude.add(url)
                    
                    return urls_to_exclude
                
                # 全リンクを統合し、重複を削除
                all_links = []
                seen_urls = set()
                
                for link_list in [header_links, footer_links, nav_links]:
                    for link in link_list:
                        url_key = link['url']
                        if url_key not in seen_urls:
                            seen_urls.add(url_key)
                            all_links.append(link)
                
                # 重複パターンを検出して除去（ベースURLを考慮）
                urls_to_exclude = detect_repeated_patterns(all_links, threshold=10, base_url=url)
                filtered_links = [link for link in all_links 
                                if link['url'] not in urls_to_exclude]

                # 見出し抽出ユーティリティ（h2/h3 を統合した単一リスト）
                def extract_headings(soup: BeautifulSoup) -> List[str]:
                    h2_list = [h.get_text(strip=True) for h in soup.find_all('h2') if h.get_text(strip=True)]
                    h3_list = [h.get_text(strip=True) for h in soup.find_all('h3') if h.get_text(strip=True)]
                    merged = h2_list + h3_list
                    # 重複除去を保持順で行う
                    seen = set()
                    unique_list: List[str] = []
                    for item in merged:
                        if item not in seen:
                            seen.add(item)
                            unique_list.append(item)
                    return unique_list[:100]

                async def fetch_headings_for_url(session: aiohttp.ClientSession, target_url: str) -> List[str]:
                    try:
                        async with session.get(target_url, headers=headers, timeout=ClientTimeout(total=15)) as resp:
                            if resp.status != 200:
                                return []
                            html_text = await resp.text()
                            page_soup = BeautifulSoup(html_text, "html.parser")
                            # ノイズになりがちな要素は落とす
                            for t in page_soup(["script", "style", "noscript"]):
                                t.decompose()
                            return extract_headings(page_soup)
                    except Exception:
                        return []

                # 同一ドメインに限定して並行で見出しを取得
                base_domain = urlparse(url).netloc.split(':')[0].lower()
                def is_same_domain(target: str) -> bool:
                    try:
                        netloc = urlparse(target).netloc.split(':')[0].lower()
                        # サブドメインも許可（example.com と www.example.com など）
                        return netloc == base_domain or netloc.endswith('.' + base_domain)
                    except Exception:
                        return False

                max_fetch = 20
                concurrency = 5
                sem = asyncio.Semaphore(concurrency)

                eligible_indices = [i for i, l in enumerate(filtered_links) if is_same_domain(l['url'])][:max_fetch]

                async def bound_fetch(idx: int, target_url: str):
                    async with sem:
                        return idx, await fetch_headings_for_url(session, target_url)

                tasks = [asyncio.create_task(bound_fetch(i, filtered_links[i]['url'])) for i in eligible_indices]
                if tasks:
                    results = await asyncio.gather(*tasks, return_exceptions=True)
                    for res in results:
                        if isinstance(res, tuple):
                            idx, headings = res
                            filtered_links[idx]["content_headings"] = headings
                # 未付与のリンクには空配列を設定
                for link_item in filtered_links:
                    if "content_headings" not in link_item:
                        link_item["content_headings"] = []
                
                logger.info(f"Successfully extracted {len(filtered_links)} links from {url}")
                
                # 結果を返す
                return json.dumps({
                    "base_url": url,
                    "total_links": len(all_links),
                    "filtered_links": len(filtered_links),
                    "links": filtered_links,
                    "sections": {
                        "header_links": len(header_links),
                        "footer_links": len(footer_links),
                        "nav_links": len(nav_links)
                    }
                }, ensure_ascii=False)
                
    except Exception as e:
        logger.exception(f"Error in extract_site_links: {e}")
        return json.dumps({
            "error": str(e),
            "base_url": url,
            "links": []
        }, ensure_ascii=False)


@mcp.tool()
async def extract_site_links_with_playwright(url: str) -> str:
    """
    Playwrightを使用してJavaScript/SPA/Reactサイトからheader/footer/navのリンクを抽出します。
    動的にレンダリングされるページに最適です。
    
    Args:
        url: 対象サイトのURL（例：「https://www.goldsgym.jp」）
    
    Returns:
        サイトのリンク情報のJSON文字列。各リンクにはtext, url、content_headings(見出しリスト)が含まれる
    """
    logger.info(f"extract_site_links_with_playwright called with url={url}")
    
    if not PLAYWRIGHT_AVAILABLE:
        error_msg = "Playwright is not available. Please install it with: pip install playwright && playwright install"
        logger.error(error_msg)
        return json.dumps({
            "error": error_msg,
            "base_url": url,
            "links": []
        }, ensure_ascii=False)
    
    if not async_playwright:
        return json.dumps({"error": "Playwright not available", "base_url": url, "links": []}, ensure_ascii=False)
    
    # PDFを事前に除外
    if url.lower().endswith('.pdf'):
        logger.warning(f"Skipping PDF: {url}")
        return json.dumps({"error": "PDF files are not supported", "base_url": url, "links": []}, ensure_ascii=False)
    
    async with browser_semaphore:  # ブラウザ数制限
        browser = None
        context = None
        page = None
        try:
            logger.debug(f"Starting Playwright link extraction for: {url}")
            async with async_playwright() as p:
                # ブラウザを起動
                browser = await p.chromium.launch(
                    headless=True,
                    args=['--no-sandbox', '--single-process']
                )
                # Contextを作成
                context = await browser.new_context(
                    viewport={'width': 1920, 'height': 1080}
                )
                page = await context.new_page()
                
                # User-Agentを設定
                await page.set_extra_http_headers({
                    "User-Agent": (
                        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                        "AppleWebKit/537.36 (KHTML, like Gecko) "
                        "Chrome/120.0.0.0 Safari/537.36"
                    ),
                    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
                    "Accept-Language": "ja,en-US;q=0.7,en;q=0.3",
                    "Accept-Encoding": "gzip, deflate",
                    "DNT": "1",
                    "Connection": "keep-alive",
                    "Upgrade-Insecure-Requests": "1",
                    "Sec-Fetch-Dest": "document",
                    "Sec-Fetch-Mode": "navigate",
                    "Sec-Fetch-Site": "none",
                    "Cache-Control": "max-age=0"
                })
                
                # ページにアクセス
                logger.debug(f"Navigating to {url}")
                await page.goto(url, wait_until="domcontentloaded", timeout=15000)
            
                # SPAの初期レンダリングを待つ
                logger.debug("Waiting for network idle")
                await page.wait_for_load_state("networkidle")
            
                # 動的要素の出現を待つ
                try:
                    await page.wait_for_selector(
                        "header, nav, footer, [role='navigation'], .header, .navbar, .navigation",
                        timeout=10000
                    )
                    logger.debug("Navigation elements found")
                except:
                    logger.warning(f"No navigation elements found immediately for {url}")
                
                # 追加の待機（動的レンダリング完了のため）
                await page.wait_for_timeout(5000)
                
                # JavaScriptでリンク数を事前確認（デバッグ用）
                js_link_info = await page.evaluate("""
                    () => {
                        return {
                            total: document.querySelectorAll('a').length,
                            inHeader: document.querySelectorAll('header a, .header a').length,
                            inNav: document.querySelectorAll('nav a, .nav a, .navbar a').length,
                            inFooter: document.querySelectorAll('footer a, .footer a').length,
                            hasHeader: !!document.querySelector('header, .header'),
                            hasNav: !!document.querySelector('nav, .nav, .navbar'),
                            hasFooter: !!document.querySelector('footer, .footer')
                        }
                    }
                """)
                logger.debug(f"Link info: {js_link_info}")
                
                # HTMLを取得
                html = await page.content()
            
            # BeautifulSoupでパース
            soup = BeautifulSoup(html, "html.parser")
            
            # スクリプトとスタイルを除去
            for tag in soup(["script", "style", "noscript"]):
                tag.decompose()
            
            # header/footer/nav要素を探す（セレクタを拡張）
            header = (soup.find("header") or 
                     soup.select_one('[role="banner"]') or
                     soup.select_one('.header') or
                     soup.select_one('#header'))
            
            footer = (soup.find("footer") or 
                     soup.select_one('[role="contentinfo"]') or
                     soup.select_one('.footer') or
                     soup.select_one('#footer'))
            
            # 独立したnav要素を探す（headerの外にあるもの）
            nav_elements = soup.find_all("nav")
            nav_elements.extend(soup.select('.nav, .navbar, .navigation'))
            
            independent_navs = []
            if header and isinstance(header, Tag):
                header_navs = header.find_all("nav")
                header_navs.extend(header.select('.nav, .navbar, .navigation'))
                independent_navs = [nav for nav in nav_elements if nav not in header_navs]
            else:
                independent_navs = nav_elements
            
            # リンクを抽出する内部関数
            def extract_links_from_element(element):
                if element is None:
                    return []
                
                links = []
                for link in element.find_all('a', href=True):
                    text = link.get_text(strip=True)
                    href = link['href']
                    
                    # tel:, mailto:, javascript: などをスキップ
                    if href.startswith(('tel:', 'mailto:', 'javascript:', '#')):
                        continue
                    
                    # 相対URLを絶対URLに変換
                    absolute_url = urljoin(url, href)
                    
                    # テキストが空でない場合のみ処理
                    if text:
                        links.append({
                            'text': text,
                            'url': absolute_url
                        })
                return links
            
            # 各セクションからリンクを抽出
            header_links = extract_links_from_element(header)
            footer_links = extract_links_from_element(footer)
            nav_links = []
            for nav in independent_navs:
                nav_links.extend(extract_links_from_element(nav))
            
            logger.debug(f"Extracted - Header: {len(header_links)}, Footer: {len(footer_links)}, Nav: {len(nav_links)}")
            
            # パターン検出と除去（既存のロジックを維持）
            def extract_url_pattern(url: str, base_url: str = "") -> str:
                """URLからパーマリンク構造のパターンを抽出（ベースURLを考慮）"""
                try:
                    parsed = urlparse(url)
                    base_parsed = urlparse(base_url)
                    
                    # ベースURLのパス部分を除外
                    base_path = base_parsed.path.strip('/')
                    full_path = parsed.path.strip('/')
                    
                    # ベースURLのパスが含まれている場合、それを除外
                    if base_path and full_path.startswith(base_path):
                        relative_path = full_path[len(base_path):].strip('/')
                    else:
                        relative_path = full_path
                    
                    if relative_path:
                        parts = relative_path.split('/')
                        if len(parts) >= 2:
                            pattern_parts = parts[:-1] + ['*']
                            return '/' + '/'.join(pattern_parts) + '/'
                    
                    return parsed.path
                except:
                    return url
            
            def detect_repeated_patterns(all_links: list, threshold: int = 10, base_url: str = "") -> set:
                """同じパーマリンク構造が閾値回数以上繰り返されるパターンを検出（ベースURLを考慮）"""
                pattern_counts = {}
                url_to_pattern = {}
                
                for link in all_links:
                    url = link['url']
                    pattern = extract_url_pattern(url, base_url)
                    
                    pattern_counts[pattern] = pattern_counts.get(pattern, 0) + 1
                    url_to_pattern[url] = pattern
                
                repeated_patterns = {pattern for pattern, count in pattern_counts.items() 
                                   if count >= threshold}
                
                urls_to_exclude = set()
                for url, pattern in url_to_pattern.items():
                    if pattern in repeated_patterns:
                        urls_to_exclude.add(url)
                
                return urls_to_exclude
            
            # 全リンクを統合し、重複を削除
            all_links = []
            seen_urls = set()
            
            for link_list in [header_links, footer_links, nav_links]:
                for link in link_list:
                    url_key = link['url']
                    if url_key not in seen_urls:
                        seen_urls.add(url_key)
                        all_links.append(link)
            
            # リンクが0件の場合の追加処理
            if len(all_links) == 0:
                logger.warning("No links extracted from BeautifulSoup. Trying JavaScript extraction...")
                
                # JavaScriptで直接リンクを取得（フォールバック）
                if async_playwright:
                    async with async_playwright() as p2:
                        browser2 = await p2.chromium.launch(headless=True, args=['--no-sandbox', '--single-process'])
                        context2 = await browser2.new_context()
                        page2 = await context2.new_page()
                    
                        await page2.goto(url, wait_until="networkidle", timeout=30000)
                        await page2.wait_for_timeout(5000)
                        
                        js_links = await page2.evaluate("""
                        () => {
                            const foundLinks = [];
                            const seen = new Set();
                            
                            document.querySelectorAll('a').forEach(link => {
                                if (link.href && 
                                    !link.href.startsWith('tel:') && 
                                    !link.href.startsWith('mailto:') &&
                                    !link.href.startsWith('javascript:') &&
                                    !seen.has(link.href)) {
                                    seen.add(link.href);
                                    foundLinks.push({
                                        text: link.innerText.trim() || link.textContent.trim() || 'No text',
                                        url: link.href
                                    });
                                }
                            });
                            
                            return foundLinks;
                        }
                        """)
                        
                        await page2.close()
                        await context2.close()
                        await browser2.close()
                        
                        all_links = js_links
                        logger.info(f"JavaScript extraction found {len(all_links)} links")
            
            # 重複パターンを検出して除去（ベースURLを考慮）
            urls_to_exclude = detect_repeated_patterns(all_links, threshold=10, base_url=url)
            filtered_links = [link for link in all_links 
                            if link['url'] not in urls_to_exclude]
            
            # 見出し抽出は簡易版（時間短縮のため）
            for link_item in filtered_links:
                link_item["content_headings"] = []
            
            logger.info(f"Successfully extracted {len(filtered_links)} links from {url}")
            
            # 結果を返す
            return json.dumps({
                "base_url": url,
                "total_links": len(all_links),
                "filtered_links": len(filtered_links),
                "links": filtered_links,
                "sections": {
                    "header_links": len(header_links),
                    "footer_links": len(footer_links),
                    "nav_links": len(nav_links)
                },
                "debug_info": js_link_info if 'js_link_info' in locals() else {}
            }, ensure_ascii=False)
                
        except Exception as e:
            logger.exception(f"Error in extract_site_links_with_playwright: {e}")
            return json.dumps({
                "error": str(e),
                "base_url": url,
                "links": []
            }, ensure_ascii=False)
        finally:
            # 完全な終了処理
            try:
                if page:
                    await page.close()
            except:
                pass
            try:
                if context:
                    await context.close()
            except:
                pass
            try:
                if browser:
                    await browser.close()
                    await asyncio.sleep(1)
            except:
                pass


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Rakuraku Media School tools
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

@mcp.tool()
async def rakuraku_school_list(
    keyword: str = "",
    per_page: int = 20,
    page: int = 1,
    status: str = "publish,draft",
    include_custom_fields: bool = False,
) -> str:
    """
    Rakuraku Media School の「school-list」カスタム投稿を検索・一覧表示します。
    WordPress 管理画面（/wp-admin/edit.php?post_type=school-list）と同等の情報を取得できます。
    
    Args:
        keyword: タイトル・本文・カスタムフィールドに対する検索語
        per_page: 取得件数 (1-100)
        page: ページ番号 (1以上)
        status: 取得する投稿ステータス（例: "publish", "draft", "publish,draft"）
        include_custom_fields: True の場合はカスタムフィールドをプレビュー表示
    """
    logger.info(
        "[Rakuraku] school-list 検索 keyword=%s, per_page=%s, page=%s",
        keyword,
        per_page,
        page,
    )
    
    if not _rakuraku_credentials_ready():
        return _rakuraku_missing_credentials_message()
    
    per_page = max(1, min(per_page, 100))
    page = max(1, page)
    
    params: Dict[str, Any] = {
        "per_page": per_page,
        "page": page,
        "status": _rakuraku_build_status_param(status),
        "context": "edit",
        "orderby": "date",
        "order": "desc",
    }
    
    if keyword:
        params["search"] = keyword
    if not include_custom_fields:
        params["_fields"] = RAKURAKU_DEFAULT_FIELDS
    
    try:
        posts, headers = await _rakuraku_wp_get(RAKURAKU_POST_TYPE, params=params)
    except RuntimeError as exc:
        logger.error("[Rakuraku] school-list 取得失敗: %s", exc)
        return f"エラー: {exc}"
    
    if not isinstance(posts, list):
        return "エラー: 予期しないレスポンス形式です。"
    if not posts:
        return "指定条件に一致する school-list 投稿は見つかりませんでした。"
    
    total_posts = headers.get("X-WP-Total", "unknown")
    total_pages = headers.get("X-WP-TotalPages", "unknown")
    
    lines = [
        f"📚 Rakuraku Media School school-list 投稿 ({len(posts)}件)",
        f"   page {page}/{total_pages} / total posts: {total_posts}",
        ""
    ]
    
    for post in posts:
        lines.append(_rakuraku_format_summary(post, include_fields=include_custom_fields))
        lines.append("")
    
    return "\n".join(lines).strip()


@mcp.tool()
async def rakuraku_school_detail(identifier: str) -> str:
    """
    school-list 投稿を ID / slug / タイトルで特定し、全文とカスタムフィールドを取得します。
    
    Args:
        identifier: 投稿ID（数値）、または slug / タイトルの一部
    """
    identifier = (identifier or "").strip()
    if not identifier:
        return "identifier を指定してください（ID, slug, タイトルの一部など）。"
    
    if not _rakuraku_credentials_ready():
        return _rakuraku_missing_credentials_message()
    
    logger.info("[Rakuraku] school-list 詳細取得 identifier=%s", identifier)
    
    try:
        post = await _rakuraku_find_post(identifier)
    except RuntimeError as exc:
        logger.error("[Rakuraku] school-list 詳細取得失敗: %s", exc)
        return f"エラー: {exc}"
    
    if not post:
        return f"identifier '{identifier}' に一致する school-list 投稿が見つかりませんでした。"
    
    return _rakuraku_format_detail(post)


@mcp.tool()
async def rakuraku_create_school_post(
    title: str,
    content: str = "",
    status: str = "draft",
    fields_json: str = "",
    excerpt: str = "",
    slug: str = ""
) -> str:
    """
    school-list カスタム投稿を新規作成します。
    """
    if not _rakuraku_credentials_ready():
        return _rakuraku_missing_credentials_message()
    
    clean_title = (title or "").strip()
    if not clean_title:
        return "タイトルを指定してください。"
    
    payload: Dict[str, Any] = {
        "title": clean_title,
        "status": _rakuraku_normalize_single_status(status),
    }
    if content:
        payload["content"] = content
    if excerpt:
        payload["excerpt"] = excerpt
    if slug:
        payload["slug"] = slug
    
    fields, error = _rakuraku_parse_fields_json(fields_json)
    if error:
        return error
    if fields:
        payload["meta"] = fields
    
    try:
        post = await _rakuraku_wp_post(RAKURAKU_POST_TYPE, payload)
    except RuntimeError as exc:
        logger.error("[Rakuraku] school-list 作成失敗: %s", exc)
        return f"❌ 作成に失敗しました。\n{exc}"
    
    return _rakuraku_format_post_action_result("✅ school-list 投稿を作成しました", post)


@mcp.tool()
async def rakuraku_update_school_post(
    post_id: int,
    title: str = "",
    content: str = "",
    status: str = "",
    fields_json: str = "",
    excerpt: str = "",
    slug: str = ""
) -> str:
    """
    school-list 投稿のタイトル / 本文 / ステータス / メタ情報を更新します。
    """
    if not _rakuraku_credentials_ready():
        return _rakuraku_missing_credentials_message()
    
    payload: Dict[str, Any] = {}
    if title:
        payload["title"] = title
    if content:
        payload["content"] = content
    if excerpt:
        payload["excerpt"] = excerpt
    if slug:
        payload["slug"] = slug
    if status:
        payload["status"] = _rakuraku_normalize_single_status(status)
    
    fields, error = _rakuraku_parse_fields_json(fields_json)
    if error:
        return error
    if fields:
        payload.setdefault("meta", {}).update(fields)
    
    if not payload:
        return "更新項目を1つ以上指定してください。"
    
    try:
        post = await _rakuraku_wp_post(f"{RAKURAKU_POST_TYPE}/{post_id}", payload)
    except RuntimeError as exc:
        logger.error("[Rakuraku] school-list 更新失敗: %s", exc)
        return f"❌ 更新に失敗しました。\n{exc}"
    
    return _rakuraku_format_post_action_result("✅ school-list 投稿を更新しました", post)


@mcp.tool()
async def rakuraku_media_posts(
    keyword: str = "",
    category_id: int = 0,
    status: str = "publish,draft",
    per_page: int = 20,
    page: int = 1,
    include_custom_fields: bool = False,
) -> str:
    """
    Rakuraku Media School の通常投稿（/wp-admin/edit.php）を検索します。
    
    Args:
        keyword: 検索語
        category_id: カテゴリーID（0で無視）
        status: 投稿ステータス（例: "publish", "draft", "publish,draft"）
        per_page: 取得件数 (1-100)
        page: ページ番号
        include_custom_fields: カスタムフィールドをプレビュー表示するか
    """
    if not _rakuraku_credentials_ready():
        return _rakuraku_missing_credentials_message()
    
    per_page = max(1, min(per_page, 100))
    page = max(1, page)
    status_param = _rakuraku_build_status_param(status)
    
    params: Dict[str, Any] = {
        "per_page": per_page,
        "page": page,
        "status": status_param,
        "context": "edit",
        "orderby": "date",
        "order": "desc",
    }
    if keyword:
        params["search"] = keyword
    if category_id > 0:
        params["categories"] = category_id
    if not include_custom_fields:
        params["_fields"] = RAKURAKU_DEFAULT_FIELDS
    
    logger.info(
        "[Rakuraku] posts 検索 keyword=%s category=%s status=%s page=%s",
        keyword,
        category_id or "any",
        status_param,
        page,
    )
    
    try:
        posts, headers = await _rakuraku_wp_get("posts", params=params)
    except RuntimeError as exc:
        logger.error("[Rakuraku] posts 取得失敗: %s", exc)
        return f"エラー: {exc}"
    
    if not isinstance(posts, list):
        return "エラー: 予期しないレスポンス形式です。"
    if not posts:
        return "指定条件に一致する投稿が見つかりませんでした。"
    
    total_posts = headers.get("X-WP-Total", "unknown")
    total_pages = headers.get("X-WP-TotalPages", "unknown")
    
    lines = [
        f"📰 Rakuraku Media School 通常投稿 ({len(posts)}件)",
        f"   page {page}/{total_pages} / total posts: {total_posts}",
        ""
    ]
    for post in posts:
        lines.append(_rakuraku_format_summary(post, include_fields=include_custom_fields))
        lines.append("")
    
    return "\n".join(lines).strip()


@mcp.tool()
async def rakuraku_create_media_post(
    title: str,
    content: str = "",
    status: str = "draft",
    fields_json: str = "",
    excerpt: str = "",
    slug: str = ""
) -> str:
    """
    通常投稿（post）を新規作成します。
    """
    if not _rakuraku_credentials_ready():
        return _rakuraku_missing_credentials_message()
    
    clean_title = (title or "").strip()
    if not clean_title:
        return "タイトルを指定してください。"
    
    payload: Dict[str, Any] = {
        "title": clean_title,
        "status": _rakuraku_normalize_single_status(status),
    }
    if content:
        payload["content"] = content
    if excerpt:
        payload["excerpt"] = excerpt
    if slug:
        payload["slug"] = slug
    
    fields, error = _rakuraku_parse_fields_json(fields_json)
    if error:
        return error
    if fields:
        payload["meta"] = fields
    
    try:
        post = await _rakuraku_wp_post("posts", payload)
    except RuntimeError as exc:
        logger.error("[Rakuraku] posts 作成失敗: %s", exc)
        return f"❌ 作成に失敗しました。\n{exc}"
    
    return _rakuraku_format_post_action_result("✅ 通常投稿を作成しました", post)


@mcp.tool()
async def rakuraku_update_media_post(
    post_id: int,
    title: str = "",
    content: str = "",
    status: str = "",
    fields_json: str = "",
    excerpt: str = "",
    slug: str = ""
) -> str:
    """
    通常投稿のタイトル / 本文 / ステータス / メタ情報を更新します。
    """
    if not _rakuraku_credentials_ready():
        return _rakuraku_missing_credentials_message()
    
    payload: Dict[str, Any] = {}
    if title:
        payload["title"] = title
    if content:
        payload["content"] = content
    if excerpt:
        payload["excerpt"] = excerpt
    if slug:
        payload["slug"] = slug
    if status:
        payload["status"] = _rakuraku_normalize_single_status(status)
    
    fields, error = _rakuraku_parse_fields_json(fields_json)
    if error:
        return error
    if fields:
        payload.setdefault("meta", {}).update(fields)
    
    if not payload:
        return "更新項目を1つ以上指定してください。"
    
    try:
        post = await _rakuraku_wp_post(f"posts/{post_id}", payload)
    except RuntimeError as exc:
        logger.error("[Rakuraku] posts 更新失敗: %s", exc)
        return f"❌ 更新に失敗しました。\n{exc}"
    
    return _rakuraku_format_post_action_result("✅ 通常投稿を更新しました", post)


@mcp.tool()
async def rakuraku_update_school_fields(
    post_id: int,
    fields_json: str,
    container: str = "meta",
    wrap_payload: bool = True,
) -> str:
    """
    school-list 投稿のカスタムフィールド/メタ情報を更新します。
    
    Args:
        post_id: 更新対象の投稿ID
        fields_json: {"フィールド名": "値"} 形式のJSON文字列
        container: custom_fields / meta / acf のいずれか（wrap_payload=True の場合）
        wrap_payload: True で JSON を container 内に包んで送信、False で JSON をそのまま送信
    """
    if not _rakuraku_credentials_ready():
        return _rakuraku_missing_credentials_message()
    
    return await _rakuraku_handle_update_tool(
        post_type=RAKURAKU_POST_TYPE,
        post_id=post_id,
        fields_json=fields_json,
        container=container,
        wrap_payload=wrap_payload,
        label=RAKURAKU_POST_TYPE,
    )


@mcp.tool()
async def rakuraku_update_media_fields(
    post_id: int,
    fields_json: str,
    container: str = "meta",
    wrap_payload: bool = True,
) -> str:
    """
    通常投稿（/wp-admin/edit.php）に対してカスタムフィールドやメタ情報を更新します。
    
    Args:
        post_id: 投稿ID
        fields_json: {"フィールド名": "値"} 形式のJSON文字列
        container: custom_fields / meta / acf （wrap_payload=True の場合）
        wrap_payload: True の場合は container 付きで送信、False で任意のpayloadを送信
    """
    if not _rakuraku_credentials_ready():
        return _rakuraku_missing_credentials_message()
    
    return await _rakuraku_handle_update_tool(
        post_type="posts",
        post_id=post_id,
        fields_json=fields_json,
        container=container,
        wrap_payload=wrap_payload,
        label="posts",
    )


@mcp.tool()
async def search_cloud_gym_introduce(
    keyword: str,
    per_page: int = 20,
    page: int = 1,
    include_terms: bool = False,
) -> str:
    """
    Cloud GYMサイトのintroduce投稿を検索するツール。

    Args:
        keyword: WordPress REST APIのsearchパラメータに渡すキーワード
        per_page: 取得件数 (1-100)
        page: ページ番号 (1以上)
        include_terms: タクソノミー情報を含めるかどうか

    Returns:
        結果を表すJSON文字列
    """
    if not keyword:
        return json.dumps(
            {
                "success": False,
                "error": "keyword_required",
                "message": "検索キーワードを指定してください。",
            },
            ensure_ascii=False,
        )

    per_page = max(1, min(per_page, 100))
    page = max(1, page)

    params: Dict[str, Any] = {
        "search": keyword,
        "per_page": per_page,
        "page": page,
        "status": "publish",
        "_fields": CLOUD_GYM_DEFAULT_FIELDS,
    }

    if include_terms:
        params["_embed"] = ""
        if "_embedded" not in params["_fields"]:
            params["_fields"] = f"{params['_fields']},_embedded"

    logger.info(
        "[CloudGym] introduce検索: %s (page=%s, per_page=%s)",
        keyword,
        page,
        per_page,
    )
    logger.debug("[CloudGym] params=%s", params)

    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(CLOUD_GYM_API_ENDPOINT, params=params) as response:
                if response.status == 200:
                    raw_posts = await response.json()
                    total_posts = response.headers.get("X-WP-Total", "unknown")
                    total_pages = response.headers.get("X-WP-TotalPages", "unknown")

                    result: Dict[str, Any] = {
                        "success": True,
                        "site": CLOUD_GYM_BASE_URL,
                        "post_type": CLOUD_GYM_POST_TYPE,
                        "search_keyword": keyword,
                        "count": len(raw_posts),
                        "pagination": {
                            "current_page": page,
                            "per_page": per_page,
                            "total_posts": total_posts,
                            "total_pages": total_pages,
                        },
                        "posts": _cloud_gym_normalize_posts(raw_posts),
                    }

                    if include_terms:
                        taxonomy_terms = _cloud_gym_extract_taxonomy_terms(raw_posts)
                        if taxonomy_terms:
                            result["taxonomy_terms"] = taxonomy_terms

                    logger.info("[CloudGym] introduce取得: %s件", len(raw_posts))
                    return json.dumps(result, ensure_ascii=False, indent=2)

                error_payload = await _cloud_gym_extract_error_payload(response)
                logger.error(
                    "[CloudGym] APIエラー (%s): %s", response.status, error_payload
                )
                return json.dumps(
                    {
                        "success": False,
                        "error": "api_error",
                        "status": response.status,
                        "details": error_payload,
                    },
                    ensure_ascii=False,
                )

    except aiohttp.ClientError as exc:
        logger.error("[CloudGym] ネットワークエラー: %s", exc)
        return json.dumps(
            {
                "success": False,
                "error": "network_error",
                "message": f"ネットワークエラーが発生しました: {str(exc)}",
            },
            ensure_ascii=False,
        )
    except Exception as exc:
        logger.exception("[CloudGym] 予期しないエラー: %s", exc)
        return json.dumps(
            {
                "success": False,
                "error": "unexpected_error",
                "message": f"予期しないエラーが発生しました: {str(exc)}",
            },
            ensure_ascii=False,
        )


@mcp.tool()
async def search_cloud_gym_posts(
    keyword: str = "",
    per_page: int = 20,
    page: int = 1,
    include_terms: bool = False,
) -> str:
    """
    Cloud GYMサイトの通常の投稿（posts）を検索・取得するツール。
    カスタム投稿タイプではなく、WordPressの標準投稿を対象とします。

    Args:
        keyword: WordPress REST APIのsearchパラメータに渡すキーワード（空文字列の場合は全件取得）
        per_page: 取得件数 (1-100)
        page: ページ番号 (1以上)
        include_terms: タクソノミー情報（カテゴリー、タグなど）を含めるかどうか

    Returns:
        結果を表すJSON文字列
    """
    per_page = max(1, min(per_page, 100))
    page = max(1, page)

    # 通常の投稿用のエンドポイント
    posts_endpoint = f"{CLOUD_GYM_BASE_URL.rstrip('/')}/wp-json/wp/v2/posts"

    params: Dict[str, Any] = {
        "per_page": per_page,
        "page": page,
        "status": "publish",
        "_fields": CLOUD_GYM_DEFAULT_FIELDS,
    }

    # キーワードが指定されている場合のみsearchパラメータを追加
    if keyword:
        params["search"] = keyword

    if include_terms:
        params["_embed"] = ""
        if "_embedded" not in params["_fields"]:
            params["_fields"] = f"{params['_fields']},_embedded"

    logger.info(
        "[CloudGym] posts検索: %s (page=%s, per_page=%s)",
        keyword or "全件",
        page,
        per_page,
    )
    logger.debug("[CloudGym] params=%s", params)

    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(posts_endpoint, params=params) as response:
                if response.status == 200:
                    raw_posts = await response.json()
                    total_posts = response.headers.get("X-WP-Total", "unknown")
                    total_pages = response.headers.get("X-WP-TotalPages", "unknown")

                    result: Dict[str, Any] = {
                        "success": True,
                        "site": CLOUD_GYM_BASE_URL,
                        "post_type": "posts",
                        "search_keyword": keyword or None,
                        "count": len(raw_posts),
                        "pagination": {
                            "current_page": page,
                            "per_page": per_page,
                            "total_posts": total_posts,
                            "total_pages": total_pages,
                        },
                        "posts": _cloud_gym_normalize_posts(raw_posts),
                    }

                    if include_terms:
                        taxonomy_terms = _cloud_gym_extract_taxonomy_terms(raw_posts)
                        if taxonomy_terms:
                            result["taxonomy_terms"] = taxonomy_terms

                    logger.info("[CloudGym] posts取得: %s件", len(raw_posts))
                    return json.dumps(result, ensure_ascii=False, indent=2)

                error_payload = await _cloud_gym_extract_error_payload(response)
                logger.error(
                    "[CloudGym] APIエラー (%s): %s", response.status, error_payload
                )
                return json.dumps(
                    {
                        "success": False,
                        "error": "api_error",
                        "status": response.status,
                        "details": error_payload,
                    },
                    ensure_ascii=False,
                )

    except aiohttp.ClientError as exc:
        logger.error("[CloudGym] ネットワークエラー: %s", exc)
        return json.dumps(
            {
                "success": False,
                "error": "network_error",
                "message": f"ネットワークエラーが発生しました: {str(exc)}",
            },
            ensure_ascii=False,
        )
    except Exception as exc:
        logger.exception("[CloudGym] 予期しないエラー: %s", exc)
        return json.dumps(
            {
                "success": False,
                "error": "unexpected_error",
                "message": f"予期しないエラーが発生しました: {str(exc)}",
            },
            ensure_ascii=False,
        )


def _cloud_gym_normalize_posts(posts: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    normalized = []
    for post in posts:
        normalized.append(
            {
                "id": post.get("id"),
                "title": _cloud_gym_extract_text_field(post.get("title")),
                "excerpt": _cloud_gym_extract_text_field(post.get("excerpt")),
                "date": post.get("date"),
                "link": post.get("link"),
                "slug": post.get("slug"),
            }
        )
    return normalized


def _cloud_gym_extract_text_field(field: Any) -> str:
    if isinstance(field, dict):
        return field.get("rendered") or field.get("raw") or ""
    if isinstance(field, str):
        return field
    return ""


def _cloud_gym_extract_taxonomy_terms(posts: List[Dict[str, Any]]) -> Dict[str, Any]:
    taxonomy_terms: Dict[str, Dict[int, Dict[str, Any]]] = {}

    for post in posts:
        embedded_terms = post.get("_embedded", {}).get("wp:term", [])
        for term_group in embedded_terms:
            for term in term_group:
                taxonomy = term.get("taxonomy")
                term_id = term.get("id")
                if taxonomy and term_id is not None:
                    taxonomy_terms.setdefault(taxonomy, {})
                    if term_id not in taxonomy_terms[taxonomy]:
                        taxonomy_terms[taxonomy][term_id] = {
                            "id": term_id,
                            "name": term.get("name", ""),
                            "slug": term.get("slug", ""),
                            "description": term.get("description", ""),
                            "count": term.get("count", 0),
                        }

    result: Dict[str, Any] = {}
    for taxonomy, terms in taxonomy_terms.items():
        result[taxonomy] = {
            "total": len(terms),
            "terms": list(terms.values()),
        }
    return result


async def _cloud_gym_extract_error_payload(response: aiohttp.ClientResponse) -> Any:
    try:
        return await response.json()
    except aiohttp.ContentTypeError:
        return await response.text()


@mcp.tool()
async def extract_store_ids_from_post(url: str) -> str:
    """
    Cloud GYMの投稿ページからパーソナルジムのストアID（store_XX形式）を抽出します。
    投稿本文を読み込んで、id属性が"store_"で始まる要素を探します。

    Args:
        url: 投稿のURL（例：「https://cloud-gym.com/personal-fitness/archives/575」）

    Returns:
        抽出されたストアIDとアンカーリンク付きURLのJSON文字列
    """
    logger.info(f"extract_store_ids_from_post called with url={url}")
    
    try:
        # 投稿ページのHTMLを取得
        headers = {
            "User-Agent": (
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/120.0.0.0 Safari/537.36"
            ),
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
            "Accept-Language": "ja,en-US;q=0.7,en;q=0.3",
        }
        
        async with aiohttp.ClientSession() as session:
            async with session.get(url, headers=headers, timeout=ClientTimeout(total=20)) as response:
                if response.status != 200:
                    error_msg = f"Failed to fetch page: {response.status}"
                    logger.error(error_msg)
                    return json.dumps({
                        "success": False,
                        "error": error_msg,
                        "url": url,
                        "store_ids": [],
                        "anchor_urls": []
                    }, ensure_ascii=False)
                
                html = await response.text()
                soup = BeautifulSoup(html, "html.parser")
                
                # store_で始まるIDを持つ要素を探す
                store_ids = set()
                
                # 1. id属性が"store_"で始まる要素を探す
                for element in soup.find_all(id=re.compile(r'^store_\d+$')):
                    store_id = element.get('id', '')
                    if store_id:
                        store_ids.add(store_id)
                
                # 2. class属性に"store_"を含む要素も探す（フォールバック）
                for element in soup.find_all(class_=re.compile(r'store_\d+')):
                    classes = element.get('class', [])
                    for cls in classes:
                        match = re.search(r'store_(\d+)', cls)
                        if match:
                            store_ids.add(f"store_{match.group(1)}")
                
                # 3. データ属性からも探す
                for element in soup.find_all(attrs={'data-store-id': True}):
                    store_id_attr = element.get('data-store-id', '')
                    if store_id_attr:
                        if not store_id_attr.startswith('store_'):
                            store_ids.add(f"store_{store_id_attr}")
                        else:
                            store_ids.add(store_id_attr)
                
                # アンカーリンク付きURLを生成
                anchor_urls = []
                for store_id in sorted(store_ids):
                    anchor_urls.append(f"{url}#{store_id}")
                
                logger.info(f"Extracted {len(store_ids)} store IDs from {url}")
                
                result = {
                    "success": True,
                    "url": url,
                    "store_ids": sorted(list(store_ids)),
                    "anchor_urls": anchor_urls,
                    "count": len(store_ids)
                }
                
                return json.dumps(result, ensure_ascii=False, indent=2)
                
    except Exception as e:
        logger.exception(f"Error in extract_store_ids_from_post: {e}")
        return json.dumps({
            "success": False,
            "error": str(e),
            "url": url,
            "store_ids": [],
            "anchor_urls": []
        }, ensure_ascii=False)


@mcp.tool()
async def generate_gym_introduction_email(
    region: str,
    per_page: int = 50,
    max_posts: int = 10
) -> str:
    """
    指定された地域のパーソナルジム投稿を検索し、メールテンプレートを生成します。
    投稿本文を読み込んで実際にパーソナルジムが存在することを確認し、
    アンカーリンク付きURLを生成してメールテンプレートに埋め込みます。

    Args:
        region: 検索する地域名（例：「東京」「大阪」「横浜」）
        per_page: 1回の検索で取得する件数 (1-100)
        max_posts: 処理する最大投稿数（実際にパーソナルジムが存在する投稿のみ）

    Returns:
        メールテンプレートと処理結果のJSON文字列
    """
    logger.info(f"generate_gym_introduction_email called with region={region}")
    
    per_page = max(1, min(per_page, 100))
    max_posts = max(1, max_posts)
    
    try:
        # 1. 地域名で投稿を検索
        posts_endpoint = f"{CLOUD_GYM_BASE_URL.rstrip('/')}/wp-json/wp/v2/posts"
        params = {
            "search": region,
            "per_page": per_page,
            "page": 1,
            "status": "publish",
            "_fields": CLOUD_GYM_DEFAULT_FIELDS,
        }
        
        async with aiohttp.ClientSession() as session:
            async with session.get(posts_endpoint, params=params) as response:
                if response.status != 200:
                    error_msg = f"Failed to fetch posts: {response.status}"
                    logger.error(error_msg)
                    return json.dumps({
                        "success": False,
                        "error": error_msg,
                        "region": region
                    }, ensure_ascii=False)
                
                raw_posts = await response.json()
                logger.info(f"Found {len(raw_posts)} posts for region: {region}")
        
        # 2. 各投稿からストアIDを抽出
        valid_posts = []
        processed_count = 0
        
        for post in raw_posts:
            if processed_count >= max_posts:
                break
            
            post_link = post.get("link", "")
            if not post_link:
                continue
            
            # 投稿からストアIDを抽出
            store_result_json = await extract_store_ids_from_post(post_link)
            store_result = json.loads(store_result_json)
            
            if store_result.get("success") and store_result.get("store_ids"):
                # パーソナルジムが実際に存在する投稿
                valid_posts.append({
                    "title": _cloud_gym_extract_text_field(post.get("title")),
                    "url": post_link,
                    "store_ids": store_result.get("store_ids", []),
                    "anchor_urls": store_result.get("anchor_urls", [])
                })
                processed_count += 1
                logger.info(f"Valid post found: {post_link} ({len(store_result.get('store_ids', []))} stores)")
        
        # 3. メールテンプレートを生成
        if not valid_posts:
            return json.dumps({
                "success": False,
                "error": "no_valid_posts",
                "message": f"地域「{region}」でパーソナルジムが存在する投稿が見つかりませんでした。",
                "region": region,
                "searched_posts": len(raw_posts)
            }, ensure_ascii=False, indent=2)
        
        # アンカーリンク付きURLを収集
        all_anchor_urls = []
        for post_info in valid_posts:
            all_anchor_urls.extend(post_info["anchor_urls"])
        
        # メールテンプレート
        url_section = "\n".join(all_anchor_urls)
        
        email_template = f"""突然のご連絡失礼いたします。
パーソナルジム比較メディア「personal-fitness」（https://cloud-gym.com/personal-fitness/）を運営しております株式会社Buildsの金藤優太と申します。

「personal-fitness」では、メディア立ち上げから順調にPV数を伸ばしており、全国のジム・パーソナルジム5,000店舗以上を紹介しているメディアとなります。

事後のご連絡となってしまい大変恐縮ですが、この度、弊社メディアにて貴社パーソナルジムをおすすめパーソナルジムとしてご紹介させていただきましたのでご連絡いたしました。

＝＝＝＝＝＝＝＝＝＝＝＝
▼この度、貴社パーソナルジムをご紹介させていただいた記事▼
{url_section}
＝＝＝＝＝＝＝＝＝＝＝＝

メディア掲載実績として貴社サイトにて記事をご紹介頂くことは可能でしょうか？

参考までに、他社様での掲載事例を以下にお示しいたします。
https://evigym.com/news/media-personal-fitness
https://corp.azure-collaboration.co.jp/media-personal-fitness/

また、記事内容に関するお問い合わせなどございましたら、ご回答させていただきますため、ご連絡していただけますと幸いです。

不躾なご連絡となり恐れ入りますが、今後ともpersonal-fitnessを何卒よろしくお願いいたします。"""
        
        result = {
            "success": True,
            "region": region,
            "searched_posts": len(raw_posts),
            "valid_posts": len(valid_posts),
            "total_stores": sum(len(p["store_ids"]) for p in valid_posts),
            "posts": valid_posts,
            "email_template": email_template,
            "anchor_urls": all_anchor_urls
        }
        
        logger.info(f"Generated email template for {len(valid_posts)} posts in {region}")
        return json.dumps(result, ensure_ascii=False, indent=2)
        
    except Exception as e:
        logger.exception(f"Error in generate_gym_introduction_email: {e}")
        return json.dumps({
            "success": False,
            "error": str(e),
            "region": region
        }, ensure_ascii=False)


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Google Sheets ツール
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def _get_google_sheets_service():
    """
    Google Sheets APIのサービスオブジェクトを取得します。
    認証情報JSONファイルは以下の順序で検索されます:
    1. 環境変数 GOOGLE_APPLICATION_CREDENTIALS
    2. server.py と同じディレクトリ
    3. ホームディレクトリの mcp-servers/scraping-mcp-server/
    """
    if not GOOGLE_SHEETS_AVAILABLE:
        raise RuntimeError(
            "Google Sheets API が利用できません。"
            "以下のパッケージをインストールしてください: google-api-python-client, google-auth"
        )
    
    # 認証情報ファイル名
    creds_filename = "braided-circuit-465415-m6-1cbbf338d9f0.json"
    
    # 検索パスのリスト
    possible_paths = []
    
    # 1. 環境変数から取得
    env_path = os.getenv("GOOGLE_APPLICATION_CREDENTIALS")
    if env_path:
        possible_paths.append(Path(env_path))
    
    # 2. server.pyと同じディレクトリ
    possible_paths.append(Path(__file__).parent / creds_filename)
    
    # 3. ホームディレクトリの mcp-servers/scraping-mcp-server/
    home_dir = Path.home()
    possible_paths.append(home_dir / "mcp-servers" / "scraping-mcp-server" / creds_filename)
    
    # 4. 開発用: Desktop/02_開発/scraping-mcp-server/
    desktop_path = home_dir / "Desktop" / "02_開発" / "scraping-mcp-server" / creds_filename
    possible_paths.append(desktop_path)
    
    # 最初に見つかったパスを使用
    creds_path = None
    for path in possible_paths:
        if path.exists():
            creds_path = path
            logger.info(f"認証情報ファイルを見つけました: {creds_path}")
            break
    
    if not creds_path:
        searched_paths = "\n".join([f"  - {p}" for p in possible_paths])
        raise RuntimeError(
            f"認証情報ファイルが見つかりません: {creds_filename}\n"
            f"以下の場所を確認しました:\n{searched_paths}\n"
            f"または環境変数 GOOGLE_APPLICATION_CREDENTIALS を設定してください。"
        )
    
    try:
        # サービスアカウントの認証情報を読み込む
        credentials = service_account.Credentials.from_service_account_file(
            creds_path,
            scopes=['https://www.googleapis.com/auth/spreadsheets.readonly']
        )
        
        # Google Sheets APIのサービスオブジェクトを作成
        service = build('sheets', 'v4', credentials=credentials)
        return service
    except Exception as e:
        logger.exception(f"Google Sheets API認証エラー: {e}")
        raise RuntimeError(f"Google Sheets APIの認証に失敗しました: {str(e)}")


@mcp.tool()
async def read_google_sheet(
    spreadsheet_id: str,
    range_name: str = "",
    sheet_name: str = ""
) -> str:
    """
    Googleスプレッドシートからデータを読み込みます。
    
    Args:
        spreadsheet_id: スプレッドシートID（URLの /d/ と /edit の間の文字列）
            例: "1BxiMVs0XRA5nFMdKvBdBZjgmUUqptlbs74OgvE2upms"
        range_name: 読み込む範囲（例: "A1:C10", "Sheet1!A1:Z100"）
            空文字列の場合はシート全体を読み込みます
        sheet_name: シート名（range_nameにシート名が含まれていない場合に使用）
            例: "Sheet1"
    
    Returns:
        スプレッドシートのデータをJSON形式で返します
    """
    logger.info(
        f"read_google_sheet called with spreadsheet_id={spreadsheet_id}, "
        f"range_name={range_name}, sheet_name={sheet_name}"
    )
    
    if not GOOGLE_SHEETS_AVAILABLE:
        return json.dumps({
            "success": False,
            "error": "google_sheets_unavailable",
            "message": (
                "Google Sheets API が利用できません。"
                "以下のパッケージをインストールしてください: "
                "google-api-python-client, google-auth"
            )
        }, ensure_ascii=False)
    
    try:
        # サービスオブジェクトを取得
        service = _get_google_sheets_service()
        
        # 範囲を構築
        if range_name:
            # range_nameにシート名が含まれているかチェック
            if '!' in range_name:
                full_range = range_name
            elif sheet_name:
                full_range = f"{sheet_name}!{range_name}"
            else:
                full_range = range_name
        elif sheet_name:
            full_range = sheet_name
        else:
            # 範囲が指定されていない場合は、最初のシート全体を読み込む
            full_range = None
        
        # スプレッドシートのメタデータを取得（シート名の確認用）
        spreadsheet_metadata = service.spreadsheets().get(
            spreadsheetId=spreadsheet_id
        ).execute()
        
        sheet_names = [sheet['properties']['title'] for sheet in spreadsheet_metadata.get('sheets', [])]
        logger.info(f"Available sheets: {sheet_names}")
        
        # データを読み込む
        if full_range:
            result = service.spreadsheets().values().get(
                spreadsheetId=spreadsheet_id,
                range=full_range
            ).execute()
        else:
            # 範囲が指定されていない場合は、最初のシート全体を読み込む
            if sheet_names:
                first_sheet = sheet_names[0]
                result = service.spreadsheets().values().get(
                    spreadsheetId=spreadsheet_id,
                    range=first_sheet
                ).execute()
            else:
                return json.dumps({
                    "success": False,
                    "error": "no_sheets",
                    "message": "スプレッドシートにシートが見つかりませんでした。"
                }, ensure_ascii=False)
        
        values = result.get('values', [])
        
        if not values:
            return json.dumps({
                "success": True,
                "spreadsheet_id": spreadsheet_id,
                "range": full_range or sheet_names[0] if sheet_names else "unknown",
                "row_count": 0,
                "data": [],
                "message": "指定された範囲にデータがありません。"
            }, ensure_ascii=False, indent=2)
        
        # データを整形
        # 最初の行をヘッダーとして扱う
        headers = values[0] if values else []
        rows = values[1:] if len(values) > 1 else []
        
        # 辞書形式のデータに変換
        data_rows = []
        for row in rows:
            row_dict = {}
            for i, header in enumerate(headers):
                row_dict[header] = row[i] if i < len(row) else ""
            data_rows.append(row_dict)
        
        result_data = {
            "success": True,
            "spreadsheet_id": spreadsheet_id,
            "range": full_range or sheet_names[0] if sheet_names else "unknown",
            "sheet_names": sheet_names,
            "row_count": len(values),
            "header_count": len(headers),
            "headers": headers,
            "data": data_rows,
            "raw_values": values  # 生データも含める
        }
        
        logger.info(f"Successfully read {len(values)} rows from spreadsheet")
        return json.dumps(result_data, ensure_ascii=False, indent=2)
        
    except HttpError as e:
        error_details = json.loads(e.content.decode('utf-8'))
        logger.error(f"Google Sheets API HTTPエラー: {error_details}")
        return json.dumps({
            "success": False,
            "error": "api_error",
            "status_code": e.resp.status,
            "message": error_details.get('error', {}).get('message', str(e)),
            "details": error_details
        }, ensure_ascii=False, indent=2)
    except RuntimeError as e:
        logger.error(f"Google Sheets 認証エラー: {e}")
        return json.dumps({
            "success": False,
            "error": "authentication_error",
            "message": str(e)
        }, ensure_ascii=False)
    except Exception as e:
        logger.exception(f"Error in read_google_sheet: {e}")
        return json.dumps({
            "success": False,
            "error": "unexpected_error",
            "message": f"予期しないエラーが発生しました: {str(e)}"
        }, ensure_ascii=False)


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# サーバー起動
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
def main():
    """MCPサーバーのエントリーポイント"""
    mcp.run(transport="stdio")

if __name__ == "__main__":
    main()
