

@tool
async def extract_site_links(url: str) -> str:
    """
    公式サイトからheader/footer/navのリンクを抽出し、仮想サイトマップを作成する
    
    Args:
        url: 対象サイトのURL（例：「https://www.goldsgym.jp」）
    
    Returns:
        サイトのリンク情報のJSON文字列。各リンクにはtext, url、content_headings(見出しリスト)が含まれる
    """
    
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
                    return json.dumps({
                        "error": f"Failed to fetch page: {response.status}",
                        "base_url": url,
                        "links": []
                    })
                
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
                
                # パターン検出と除去（app.pyのロジック）
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
        return json.dumps({
            "error": str(e),
            "base_url": url,
            "links": []
        })

@tool
async def extract_site_links_with_playwright(url: str) -> str:
    """
    Playwrightを使用してJavaScript/SPA/Reactサイトからheader/footer/navのリンクを抽出
    
    Args:
        url: 対象サイトのURL（例：「https://www.goldsgym.jp」）
    
    Returns:
        サイトのリンク情報のJSON文字列。各リンクにはtext, url、content_headings(見出しリスト)が含まれる
    """
    
    if not PLAYWRIGHT_AVAILABLE:
        return json.dumps({
            "error": "Playwright is not available",
            "base_url": url,
            "links": []
        })
    
    if not async_playwright:
        return json.dumps({"error": "Playwright not available", "base_url": url, "links": []})
    
    # PDFを事前に除外
    if url.lower().endswith('.pdf'):
        print(f"[PLAYWRIGHT] Skipping PDF: {url}")
        return json.dumps({"error": "PDF files are not supported", "base_url": url, "links": []})
    
    async with browser_semaphore:  # ブラウザ数制限
        browser = None
        try:
            print(f"[PLAYWRIGHT] Starting extraction for: {url}")
            async with async_playwright() as p:
                # ブラウザを起動
                browser = await p.chromium.launch(
                    headless=True,
                    args=['--no-sandbox', '--single-process']
                )
                page = await browser.new_page()
                
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
                print(f"[PLAYWRIGHT] Navigating to {url}")
                await page.goto(url, wait_until="domcontentloaded", timeout=15000)  # 15秒に短縮
            
                # SPAの初期レンダリングを待つ
                print(f"[PLAYWRIGHT] Waiting for network idle")
                await page.wait_for_load_state("networkidle")
            
                # 動的要素の出現を待つ
                try:
                    await page.wait_for_selector(
                        "header, nav, footer, [role='navigation'], .header, .navbar, .navigation",
                        timeout=10000
                    )
                    print(f"[PLAYWRIGHT] Navigation elements found")
                except:
                    print(f"[WARNING] No navigation elements found immediately for {url}")
                
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
                print(f"[PLAYWRIGHT] Link info: {js_link_info}")
                
                # HTMLを取得
                html = await page.content()
                
                # ブラウザを閉じる - try内で閉じる（正常終了時）
                await browser.close()
                browser = None
            
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
            
            print(f"[PLAYWRIGHT] Extracted - Header: {len(header_links)}, Footer: {len(footer_links)}, Nav: {len(nav_links)}")
            
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
                print(f"[WARNING] No links extracted from BeautifulSoup. Trying JavaScript extraction...")
                
                # JavaScriptで直接リンクを取得（フォールバック）
                if async_playwright:
                    async with async_playwright() as p2:
                        browser2 = await p2.chromium.launch(headless=True)
                        page2 = await browser2.new_page()
                    
                        await page2.goto(url, wait_until="networkidle", timeout=30000)
                        await page2.wait_for_timeout(5000)
                        
                        js_links = await page2.evaluate("""
                        () => {
                            const selectors = [
                                'a', // 全てのリンクを取得
                            ];
                            
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
                        
                        await browser2.close()
                        
                        all_links = js_links
                        print(f"[PLAYWRIGHT] JavaScript extraction found {len(all_links)} links")
            
            # 重複パターンを検出して除去（ベースURLを考慮）
            urls_to_exclude = detect_repeated_patterns(all_links, threshold=10, base_url=url)
            filtered_links = [link for link in all_links 
                            if link['url'] not in urls_to_exclude]
            
            # 見出し抽出は簡易版（時間短縮のため）
            for link_item in filtered_links:
                link_item["content_headings"] = []
            
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
            print(f"[ERROR] Failed to extract links: {str(e)}")
            return json.dumps({
                "error": str(e),
                "base_url": url,
                "links": []
            })
        finally:
            # 必ずブラウザを閉じる
            if browser:
                try:
                    await browser.close()
                except:
                    pass

