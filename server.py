# server.py
# Webスクレイピング用MCPサーバー

import logging
import asyncio
import json
from urllib.parse import urljoin, urlparse
from typing import List
from bs4 import BeautifulSoup
from bs4.element import Tag
from mcp.server.fastmcp import FastMCP
import aiohttp
from aiohttp import ClientTimeout

# Playwrightのインポート
try:
    from playwright.async_api import async_playwright
    PLAYWRIGHT_AVAILABLE = True
except ImportError:
    async_playwright = None
    PLAYWRIGHT_AVAILABLE = False

# ログ設定
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('/Users/yuta/Desktop/02_開発/scraping-mcp-server/debug.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# ブラウザ数制限
MAX_BROWSERS = 5
browser_semaphore = asyncio.Semaphore(MAX_BROWSERS)

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
# サーバー起動
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
def main():
    """MCPサーバーのエントリーポイント"""
    mcp.run(transport="stdio")

if __name__ == "__main__":
    main()
