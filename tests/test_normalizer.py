from wa_link_parser.normalizer import normalize_url, TRACKING_PARAMS


class TestNormalizeUrl:
    # --- Scheme normalization ---

    def test_http_upgraded_to_https(self):
        assert normalize_url("http://example.com/page") == "https://example.com/page"

    def test_https_unchanged(self):
        assert normalize_url("https://example.com/page") == "https://example.com/page"

    def test_no_scheme_gets_https(self):
        assert normalize_url("example.com/page") == "https://example.com/page"

    # --- Domain normalization ---

    def test_domain_lowercased(self):
        assert normalize_url("https://YOUTUBE.COM/watch?v=abc") == "https://youtube.com/watch?v=abc"

    def test_mixed_case_domain(self):
        assert normalize_url("https://GitHub.Com/user/repo") == "https://github.com/user/repo"

    # --- Fragment removal ---

    def test_fragment_stripped(self):
        assert normalize_url("https://example.com/page#section") == "https://example.com/page"

    def test_fragment_with_query_stripped(self):
        result = normalize_url("https://example.com/page?key=val#anchor")
        assert "#anchor" not in result
        assert "key=val" in result

    # --- Tracking parameter removal ---

    def test_utm_source_stripped(self):
        url = "https://example.com/article?utm_source=whatsapp"
        assert normalize_url(url) == "https://example.com/article"

    def test_utm_all_stripped(self):
        url = "https://example.com/?utm_source=fb&utm_medium=social&utm_campaign=promo"
        assert normalize_url(url) == "https://example.com/"

    def test_fbclid_stripped(self):
        url = "https://example.com/page?fbclid=IwAR1abc123"
        assert normalize_url(url) == "https://example.com/page"

    def test_gclid_stripped(self):
        url = "https://example.com/?gclid=abc123"
        assert normalize_url(url) == "https://example.com/"

    def test_igshid_stripped(self):
        url = "https://www.instagram.com/p/ABC/?igshid=xyz"
        assert normalize_url(url) == "https://www.instagram.com/p/ABC/"

    def test_spotify_si_stripped(self):
        url = "https://open.spotify.com/track/ABC?si=sessiontoken123"
        assert normalize_url(url) == "https://open.spotify.com/track/ABC"

    def test_mc_cid_stripped(self):
        url = "https://example.com/?mc_cid=abc&mc_eid=def"
        assert normalize_url(url) == "https://example.com/"

    def test_ga_stripped(self):
        url = "https://example.com/?_ga=2.123456789.1&other=keep"
        result = normalize_url(url)
        assert "_ga" not in result
        assert "other=keep" in result

    # --- Mixed: tracking removed, legitimate kept ---

    def test_legitimate_params_preserved(self):
        url = "https://www.youtube.com/watch?v=dQw4w9WgXcQ&utm_source=wa"
        result = normalize_url(url)
        assert "v=dQw4w9WgXcQ" in result
        assert "utm_source" not in result

    def test_multiple_legitimate_params_preserved(self):
        url = "https://example.com/search?q=python&page=2&utm_medium=share"
        result = normalize_url(url)
        assert "q=python" in result
        assert "page=2" in result
        assert "utm_medium" not in result

    # --- Query param sorting ---

    def test_query_params_sorted(self):
        url = "https://example.com/?z=last&a=first&m=middle"
        result = normalize_url(url)
        assert result == "https://example.com/?a=first&m=middle&z=last"

    def test_same_params_different_order_normalize_equal(self):
        url1 = "https://example.com/?b=2&a=1"
        url2 = "https://example.com/?a=1&b=2"
        assert normalize_url(url1) == normalize_url(url2)

    # --- Empty query string cleanup ---

    def test_only_tracking_params_leaves_no_query_string(self):
        url = "https://example.com/page?utm_source=wa&fbclid=abc"
        result = normalize_url(url)
        assert result == "https://example.com/page"
        assert "?" not in result

    def test_no_trailing_question_mark(self):
        url = "https://example.com/?utm_campaign=x"
        result = normalize_url(url)
        assert not result.endswith("?")

    # --- Non-HTTP schemes passed through unchanged ---

    def test_tel_scheme_unchanged(self):
        assert normalize_url("tel:+1234567890") == "tel:+1234567890"

    def test_mailto_scheme_unchanged(self):
        assert normalize_url("mailto:user@example.com") == "mailto:user@example.com"

    # --- Already clean URL unchanged ---

    def test_clean_url_unchanged(self):
        url = "https://github.com/user/repo"
        assert normalize_url(url) == url

    def test_empty_string(self):
        assert normalize_url("") == ""

    # --- Complex real-world examples ---

    def test_amazon_affiliate_cleaned(self):
        url = "https://www.amazon.in/dp/B09XYZ?ref=cm_sw_r_wa_dp&utm_source=whatsapp"
        result = normalize_url(url)
        assert "utm_source" not in result
        assert "ref=" not in result
        assert "amazon.in" in result
        assert "B09XYZ" in result

    def test_youtube_share_link_cleaned(self):
        url = "https://youtu.be/dQw4w9WgXcQ?si=abc123xyz"
        result = normalize_url(url)
        assert "si=" not in result
        assert "dQw4w9WgXcQ" in result

    def test_twitter_tracking_cleaned(self):
        url = "https://twitter.com/user/status/123?twclid=abc&s=20"
        result = normalize_url(url)
        assert "twclid" not in result


class TestTrackingParams:
    def test_utm_params_in_set(self):
        assert "utm_source" in TRACKING_PARAMS
        assert "utm_medium" in TRACKING_PARAMS
        assert "utm_campaign" in TRACKING_PARAMS

    def test_common_trackers_in_set(self):
        assert "fbclid" in TRACKING_PARAMS
        assert "gclid" in TRACKING_PARAMS
        assert "igshid" in TRACKING_PARAMS
        assert "msclkid" in TRACKING_PARAMS
        assert "si" in TRACKING_PARAMS
