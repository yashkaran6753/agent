# src/frameworks/detector.py
from playwright.async_api import Page
from loguru import logger
import re
from Wappalyzer import Wappalyzer, WebPage

class FrameworkDetector:
    @staticmethod
    async def detect(page: Page, html_size: int = 0) -> str:
        """
        Enhanced detection: Returns 'scrapy' for static sites, 'playwright' for dynamic,
        'browser-use' for heavy bot-blockers, with detailed tech stack analysis.
        """
        try:
            # Get comprehensive tech analysis
            tech_info = await FrameworkDetector._analyze_tech_stack(page)
            
            # Print clean summary
            summary = FrameworkDetector._format_tech_summary(tech_info)
            logger.info(f"🔍 Tech Stack: {summary}")
            
            # Decision logic based on tech analysis
            if tech_info.get("is_bot_protected", False) or tech_info.get("heavy_js", False):
                if any([tech_info.get("react"), tech_info.get("vue"), tech_info.get("angular")]):
                    logger.info("🛡️  Detected heavy JS SPA with bot protection → browser-use")
                    return "browser-use"
            
            if tech_info.get("is_static", False):
                logger.info("📄 Detected static site → scrapy")
                return "scrapy"
            
            if tech_info.get("has_api", False) or tech_info.get("ssr", False):
                logger.info("🔌 Detected API-driven or SSR site → playwright")
                return "playwright"
            
            logger.info("🎮 Default → playwright")
            return "playwright"
        except Exception as e:
            logger.warning(f"Tech detection failed, falling back to playwright: {e}")
            return "playwright"
    
    @staticmethod
    async def _analyze_tech_stack(page: Page) -> dict:
        """
        Comprehensive tech stack analysis returning detailed information.
        """
        try:
            # Get page content and headers
            url = page.url
            response = await page.request.get(url)
            headers = dict(response.headers) if response else {}
            content = await page.content()
        except Exception as e:
            logger.warning(f"Failed to fetch page content/headers: {e}")
            return {"error": "fetch_failed"}
        
        try:
            # Wappalyzer analysis
            wappalyzer_results = {}
            try:
                wappalyzer = Wappalyzer.latest()  # Initialize Wappalyzer
                webpage = WebPage.new_from_url(url)
                wappalyzer_results = wappalyzer.analyze(webpage)
            except Exception as e:
                logger.warning(f"Wappalyzer failed: {e}")

            # JavaScript-based detection
            js_flags = await page.evaluate(
                """() => ({
                    // Framework globals
                    react: !!window.__REACT_DEVTOOLS_GLOBAL_HOOK__ || !!window.React,
                    vue: !!window.__VUE__ || !!window.Vue,
                    angular: !!window.angular || !!window.ng,
                    svelte: !!window.__SVELTE__,
                    ember: !!window.Ember,
                    backbone: !!window.Backbone,
                    knockout: !!window.ko,
                    polymer: !!window.Polymer,

                    // Enhanced React detection for SSR and hydrated apps
                    react_components: !!document.querySelector('[data-reactroot], [data-reactid], [data-react-class]'),
                    react_hydrated: !!document.querySelector('._reactRoot, .react-root, [data-reactroot]'),
                    
                    // SSR markers
                    nextjs: !!window.__NEXT_DATA__,
                    nuxt: !!window.__NUXT__,
                    gatsby: !!window.__GATSBY__,
                    vue_ssr: !!window.__VUE_SSR_CONTEXT__,
                    
                    // State management
                    redux: !!window.__REDUX_DEVTOOLS_EXTENSION__,
                    vuex: !!window.__VUE_DEVTOOLS_GLOBAL_HOOK__,
                    
                    // Build tools
                    webpack: !!window.webpackJsonp,
                    vite: !!window.__vite__,
                    
                    // Content analysis
                    script_count: document.querySelectorAll('script').length,
                    link_count: document.querySelectorAll('a').length,
                    form_count: document.querySelectorAll('form').length,
                    api_scripts: document.querySelectorAll('script[src*="api"], script[src*="graphql"]').length,
                    
                    // Dynamic content indicators
                    has_event_listeners: document.querySelectorAll('[onclick], [onchange], [onsubmit]').length > 0,
                    has_dynamic_classes: document.querySelectorAll('[class*="active"], [class*="show"], [class*="hide"]').length > 0,
                    
                    // Bot protection indicators (enhanced)
                    has_recaptcha: !!document.querySelector('[class*="recaptcha"], [id*="recaptcha"]'),
                    has_cloudflare: !!document.querySelector('script[src*="cloudflare"]') || !!document.querySelector('[id*="cf-"]'),
                    has_akamai: !!document.querySelector('script[src*="akamai"]'),
                    has_perimeterx: !!document.querySelector('script[src*="perimeterx"]') || !!document.querySelector('[id*="px-"]'),
                    has_imperva: !!document.querySelector('script[src*="imperva"]'),
                    
                    // Ghost CMS indicators
                    ghost_data_attrs: document.querySelectorAll('[data-ghost]').length > 0,
                    ghost_api_endpoints: document.querySelectorAll('script[src*="/ghost/api/"], script[src*="/members/api/"]').length > 0,
                    ghost_classes: document.querySelectorAll('[class*="ghost"], [class*="post-full"], [class*="kg-"]').length > 0,
                    
                    // Additional CMS indicators
                    has_cms_meta: !!document.querySelector('meta[name="generator"][content*="wordpress"], meta[name="generator"][content*="drupal"], meta[name="generator"][content*="joomla"]'),
                    has_wp_content: document.querySelectorAll('script[src*="wp-content"], link[href*="wp-content"]').length > 0,
                })"""
            )
        except Exception as e:
            logger.warning(f"JavaScript evaluation failed: {e}")
            js_flags = {}
        
        try:
            # HTML-based detection
            html_flags = FrameworkDetector._analyze_html(content)
        except Exception as e:
            logger.warning(f"HTML analysis failed: {e}")
            html_flags = {}
        
        try:
            # Header-based detection
            header_flags = FrameworkDetector._analyze_headers(headers)
        except Exception as e:
            logger.warning(f"Header analysis failed: {e}")
            header_flags = {}
        
        # Combine all detections
        tech_info = {**js_flags, **html_flags, **header_flags}
        
        # Ensure required keys exist with defaults
        tech_info.setdefault("script_count", 0)
        tech_info.setdefault("link_count", 0)
        tech_info.setdefault("form_count", 0)
        tech_info.setdefault("api_scripts", 0)
        tech_info.setdefault("has_event_listeners", False)
        
        # Add Wappalyzer results (convert set to list for JSON serialization)
        tech_info["wappalyzer"] = list(wappalyzer_results) if isinstance(wappalyzer_results, set) else wappalyzer_results
        
        # Enhanced React detection (combine multiple signals)
        tech_info["react"] = (
            tech_info.get("react") or 
            tech_info.get("react_components") or 
            tech_info.get("react_hydrated") or
            "React" in wappalyzer_results or
            tech_info.get("nextjs")
        )
        
        # Enhanced static site detection (more accurate)
        tech_info["is_static"] = (
            tech_info["script_count"] < 5 and 
            tech_info["link_count"] > 20 and 
            not any([tech_info.get("react"), tech_info.get("vue"), tech_info.get("angular"), tech_info.get("svelte")]) and
            not tech_info.get("has_api", False) and
            tech_info.get("form_count", 0) < 5 and
            not tech_info.get("has_event_listeners", False)
        )
        
        tech_info["heavy_js"] = tech_info["script_count"] > 20 or tech_info.get("webpack", False)
        tech_info["has_api"] = tech_info["api_scripts"] > 0
        tech_info["ssr"] = any([tech_info.get("nextjs"), tech_info.get("nuxt"), tech_info.get("vue_ssr")])
        tech_info["spa"] = any([tech_info.get("react"), tech_info.get("vue"), tech_info.get("angular")]) and not tech_info["ssr"]
        tech_info["is_bot_protected"] = any([
            tech_info.get("has_recaptcha"), 
            tech_info.get("has_cloudflare"), 
            tech_info.get("has_akamai"),
            tech_info.get("has_perimeterx"),
            tech_info.get("has_imperva")
        ])
        
        # Enhanced CMS detection
        tech_info["ghost_cms"] = any([
            tech_info.get("ghost_data_attrs", 0) > 0,
            tech_info.get("ghost_api_endpoints", 0) > 0,
            tech_info.get("ghost_classes", 0) > 0,
            "Ghost" in wappalyzer_results
        ])
        
        # WordPress detection enhancement
        tech_info["wordpress"] = (
            tech_info.get("wordpress") or
            tech_info.get("has_wp_content") or
            tech_info.get("has_cms_meta") or
            "WordPress" in wappalyzer_results
        )
        
        return tech_info
    
    @staticmethod
    def _format_tech_summary(tech_info: dict) -> str:
        """Create a clean, readable tech stack summary."""
        tech_info = tech_info or {}
        tech_info.setdefault("script_count", 0)
        tech_info.setdefault("link_count", 0)
        tech_info.setdefault("form_count", 0)
        tech_info.setdefault("has_api", False)
        
        summary_parts = []
        
        # Server info
        if tech_info.get("server"):
            server_name = tech_info["server"].title()
            if tech_info.get("nginx"): server_name = "Nginx"
            elif tech_info.get("apache"): server_name = "Apache"
            elif tech_info.get("iis"): server_name = "IIS"
            summary_parts.append(f"Server: {server_name}")
        
        # Site type with refined logic
        cms_detected = any([
            tech_info.get("wordpress"), tech_info.get("drupal"), tech_info.get("joomla"),
            tech_info.get("ghost_cms"), tech_info.get("jekyll"), tech_info.get("hugo"),
            tech_info.get("medium"), tech_info.get("squarespace"), tech_info.get("wix"),
            tech_info.get("shopify"),
        ])
        
        # Check Wappalyzer for CMS technologies (generic detection)
        wappalyzer_cms_indicators = {"WordPress", "Drupal", "Joomla", "Ghost", "Shopify", 
                                    "Wix", "Squarespace", "Medium", "Blogger", "Webflow"}
        wappalyzer_techs = tech_info.get("wappalyzer", set())
        cms_from_wappalyzer = any(cms in wappalyzer_techs for cms in wappalyzer_cms_indicators)
        
        if tech_info.get("is_static"):
            summary_parts.append("Type: Static site")
        elif tech_info.get("spa"):
            summary_parts.append("Type: Single Page Application")
        elif tech_info.get("ssr"):
            summary_parts.append("Type: Server-Side Rendered")
        elif cms_detected or cms_from_wappalyzer:
            # Build CMS name list from multiple sources
            cms_names = []
            
            # From HTML/JS detection
            if tech_info.get("wordpress"): cms_names.append("WordPress")
            if tech_info.get("drupal"): cms_names.append("Drupal")
            if tech_info.get("joomla"): cms_names.append("Joomla")
            if tech_info.get("ghost_cms"): cms_names.append("Ghost")
            if tech_info.get("jekyll"): cms_names.append("Jekyll")
            if tech_info.get("hugo"): cms_names.append("Hugo")
            if tech_info.get("shopify"): cms_names.append("Shopify")
            if tech_info.get("squarespace"): cms_names.append("Squarespace")
            if tech_info.get("wix"): cms_names.append("Wix")
            if tech_info.get("medium"): cms_names.append("Medium")
            
            # From Wappalyzer (only if not already in list)
            for cms in wappalyzer_cms_indicators:
                if cms in wappalyzer_techs and cms not in cms_names:
                    cms_names.append(cms)
            
            if cms_names:
                # Remove duplicates and sort
                unique_cms = sorted(list(dict.fromkeys(cms_names)))
                summary_parts.append(f"Type: {', '.join(unique_cms)}-powered site")
            else:
                summary_parts.append("Type: CMS-powered site")
        else:
            summary_parts.append("Type: Traditional website")
        
        # Frameworks detection
        frameworks = []
        
        # JavaScript frameworks from detection
        if tech_info.get("react"): frameworks.append("React")
        if tech_info.get("vue"): frameworks.append("Vue.js")
        if tech_info.get("angular"): frameworks.append("Angular")
        if tech_info.get("svelte"): frameworks.append("Svelte")
        if tech_info.get("nextjs"): frameworks.append("Next.js")
        if tech_info.get("nuxt"): frameworks.append("Nuxt.js")
        if tech_info.get("gatsby"): frameworks.append("Gatsby")
        
        # Add Wappalyzer frameworks (filter out CMS and non-framework tech)
        wappalyzer_frameworks = list(tech_info.get("wappalyzer", set()))
        framework_keywords = {"React", "Vue", "Angular", "Svelte", "Next.js", "Nuxt.js", 
                             "Gatsby", "Ember", "Backbone", "jQuery", "Bootstrap", 
                             "Tailwind", "Webpack", "Vite", "Node.js"}
        
        for tech in wappalyzer_frameworks:
            # Check if this looks like a framework (not server/CMS)
            if any(keyword in tech for keyword in framework_keywords):
                if tech not in frameworks:
                    frameworks.append(tech)
            # Special case: Ghost might be detected on non-Ghost sites
            elif tech == "Ghost" and not tech_info.get("ghost_cms") and tech_info.get("script_count", 0) > 100:
                logger.debug("Filtered out false Ghost detection on script-heavy site")
                continue
        
        if frameworks:
            # Deduplicate and sort
            unique_frameworks = sorted(list(dict.fromkeys(frameworks)))
            summary_parts.append(f"Frameworks: {', '.join(unique_frameworks)}")
        else:
            summary_parts.append("Frameworks: None detected")
        
        # Additional features
        features = []
        if tech_info.get("jquery"): features.append("jQuery")
        if tech_info.get("bootstrap"): features.append("Bootstrap")
        if tech_info.get("tailwind"): features.append("Tailwind CSS")
        if tech_info.get("is_bot_protected"): features.append("Bot protection")
        if tech_info.get("cached"): features.append("Cached")
        if tech_info.get("has_api"): features.append("API integration")
        if tech_info.get("heavy_js"): features.append("Heavy JavaScript")
        
        if features:
            summary_parts.append(f"Features: {', '.join(features)}")
        
        return " | ".join(summary_parts)
    
    @staticmethod
    def _analyze_html(content: str) -> dict:
        """Analyze HTML content for tech indicators."""
        flags = {}
        
        # Meta generators (enriched)
        generator_match = re.search(r'<meta name="generator" content="([^"]+)"', content, re.IGNORECASE)
        if generator_match:
            generator = generator_match.group(1).lower()
            flags["generator"] = generator
            
            # Generic CMS detection from generator
            cms_platforms = {
                "wordpress": "wordpress",
                "drupal": "drupal", 
                "joomla": "joomla",
                "jekyll": "jekyll",
                "hugo": "hugo",
                "ghost": "ghost",
                "medium": "medium",
                "squarespace": "squarespace",
                "wix": "wix",
                "shopify": "shopify",
                "blogger": "blogger",
                "webflow": "webflow"
            }
            
            for cms_name, flag_name in cms_platforms.items():
                if cms_name in generator:
                    flags[flag_name] = True
        
        # Framework-specific patterns (generic)
        flags["bootstrap"] = re.search(r'bootstrap(?:\.min)?\.(?:css|js)', content, re.IGNORECASE) is not None
        flags["tailwind"] = 'tailwind' in content.lower() and 'tailwindcss' in content.lower()
        flags["jquery"] = re.search(r'jquery(?:\.min)?\.js', content, re.IGNORECASE) is not None
        
        # CDN patterns (generic)
        cdn_patterns = {
            "jquery_cdn": r'code\.jquery\.com',
            "bootstrap_cdn": r'(?:stackpath\.bootstrapcdn\.com|cdn\.jsdelivr\.net/npm/bootstrap)',
            "react_cdn": r'(?:unpkg\.com/react|cdn\.jsdelivr\.net/npm/react)',
            "vue_cdn": r'cdn\.jsdelivr\.net/npm/vue',
            "fontawesome_cdn": r'kit\.fontawesome\.com|use\.fontawesome\.com'
        }
        
        for flag_name, pattern in cdn_patterns.items():
            flags[flag_name] = re.search(pattern, content, re.IGNORECASE) is not None
        
        # Server-side indicators (generic)
        flags["php"] = re.search(r'\.php\b|<\?php', content) is not None
        flags["asp"] = re.search(r'\.asp\b|<%@', content, re.IGNORECASE) is not None
        flags["jsp"] = re.search(r'\.jsp\b|<%@', content, re.IGNORECASE) is not None
        flags["ruby"] = re.search(r'\.rb\b|require.*ruby', content, re.IGNORECASE) is not None
        
        # Additional CMS indicators (generic)
        flags["wordpress_theme"] = 'wp-content/themes/' in content
        flags["wordpress_plugin"] = 'wp-content/plugins/' in content
        flags["drupal_modules"] = re.search(r'sites/all/modules/|modules/contrib/', content) is not None
        flags["shopify_store"] = re.search(r'shopify\.com/cdn/|\.myshopify\.com', content) is not None
        
        return flags
    
    @staticmethod
    def _analyze_headers(headers: dict) -> dict:
        """Analyze HTTP headers for tech indicators."""
        flags = {}
        
        server = headers.get("server", "").lower()
        flags["server"] = server
        flags["nginx"] = "nginx" in server
        flags["apache"] = "apache" in server
        flags["iis"] = "iis" in server
        flags["cloudflare"] = "cloudflare" in server
        flags["vercel"] = "vercel" in server
        
        # Framework headers (generic)
        powered_by = headers.get("x-powered-by", "").lower()
        flags["express"] = "express" in powered_by
        flags["django"] = "django" in powered_by
        flags["rails"] = "rails" in powered_by
        flags["laravel"] = "laravel" in powered_by
        flags["aspnet"] = "asp.net" in powered_by
        flags["php"] = "php" in powered_by
        
        # CDN headers (generic)
        flags["cloudflare"] = flags.get("cloudflare") or "cf-ray" in headers
        flags["akamai"] = "akamai" in server.lower() or "x-akamai" in headers
        flags["fastly"] = "fastly" in server.lower() or "x-fastly" in headers
        flags["cloudfront"] = "cloudfront" in headers.get("via", "").lower()
        
        # Better cache detection (generic)
        cache_control = headers.get("cache-control", "").lower()
        expires = headers.get("expires", "")
        pragma = headers.get("pragma", "").lower()
        
        # Generic cache detection logic
        flags["cached"] = (
            "public" in cache_control or 
            "max-age=" in cache_control or
            "s-maxage" in cache_control or
            (expires and "no-cache" not in cache_control and 
             "private" not in cache_control and 
             "no-store" not in cache_control)
        )
        
        # Store the actual header for debugging
        flags["cache_control_header"] = cache_control
        
        # Additional security/bot headers
        flags["has_security_headers"] = any(
            h in headers for h in ["x-frame-options", "content-security-policy", 
                                  "strict-transport-security", "x-content-type-options"]
        )
        
        return flags