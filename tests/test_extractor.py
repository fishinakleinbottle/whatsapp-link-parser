from wa_link_parser.extractor import extract_links, classify_url


class TestExtractLinks:
    def test_extract_single_url(self):
        links = extract_links("Check this https://www.youtube.com/watch?v=abc123")
        assert len(links) == 1
        assert links[0].link_type == "youtube"
        assert "youtube.com" in links[0].domain

    def test_extract_multiple_urls(self):
        text = "Links: https://github.com/user/repo and https://www.amazon.in/dp/123"
        links = extract_links(text)
        assert len(links) == 2
        domains = {l.domain for l in links}
        assert "github.com" in domains or "www.github.com" in domains
        assert "www.amazon.in" in domains or "amazon.in" in domains

    def test_no_urls(self):
        links = extract_links("Just a regular message with no links")
        assert len(links) == 0

    def test_general_fallback(self):
        links = extract_links("Visit https://example.com/page")
        assert len(links) == 1
        assert links[0].link_type == "general"

    def test_raw_url_preserved(self):
        """raw_url holds the original; url is the normalized form."""
        raw = "https://example.com/page?utm_source=whatsapp"
        links = extract_links(f"Check this {raw}")
        assert len(links) == 1
        assert links[0].raw_url == raw
        assert "utm_source" not in links[0].url

    def test_tracking_params_stripped_from_url(self):
        links = extract_links("See https://youtu.be/dQw4w9WgXcQ?si=abc123")
        assert len(links) == 1
        assert "si=" not in links[0].url
        assert "dQw4w9WgXcQ" in links[0].url

    def test_same_url_different_tracking_deduped_within_message(self):
        """Two URLs that normalize to the same thing should produce one ExtractedLink."""
        text = ("https://example.com/page?utm_source=wa "
                "https://example.com/page?utm_source=fb")
        links = extract_links(text)
        assert len(links) == 1
        assert links[0].url == "https://example.com/page"


class TestClassifyUrl:
    def test_youtube(self):
        _, link_type = classify_url("https://www.youtube.com/watch?v=abc")
        assert link_type == "youtube"

    def test_youtu_be(self):
        _, link_type = classify_url("https://youtu.be/abc123")
        assert link_type == "youtube"

    def test_google_maps(self):
        _, link_type = classify_url("https://maps.app.goo.gl/abc123")
        assert link_type == "google_maps"

    def test_google_docs(self):
        _, link_type = classify_url("https://docs.google.com/document/d/123/edit")
        assert link_type == "document"

    def test_instagram(self):
        _, link_type = classify_url("https://www.instagram.com/p/ABC123/")
        assert link_type == "instagram"

    def test_twitter(self):
        _, link_type = classify_url("https://twitter.com/user/status/123")
        assert link_type == "twitter"

    def test_x_com(self):
        _, link_type = classify_url("https://x.com/user/status/123")
        assert link_type == "twitter"

    def test_spotify(self):
        _, link_type = classify_url("https://open.spotify.com/playlist/abc")
        assert link_type == "spotify"

    def test_reddit(self):
        _, link_type = classify_url("https://www.reddit.com/r/bali/comments/abc")
        assert link_type == "reddit"

    def test_linkedin(self):
        _, link_type = classify_url("https://www.linkedin.com/in/user")
        assert link_type == "linkedin"

    def test_medium(self):
        _, link_type = classify_url("https://medium.com/@user/article-title")
        assert link_type == "article"

    def test_github(self):
        _, link_type = classify_url("https://github.com/user/repo")
        assert link_type == "github"

    def test_stackoverflow(self):
        _, link_type = classify_url("https://stackoverflow.com/questions/123")
        assert link_type == "stackoverflow"

    def test_amazon_in(self):
        _, link_type = classify_url("https://www.amazon.in/dp/B09XYZ1234")
        assert link_type == "shopping"

    def test_flipkart(self):
        _, link_type = classify_url("https://www.flipkart.com/product")
        assert link_type == "shopping"

    def test_zomato(self):
        _, link_type = classify_url("https://www.zomato.com/bali/restaurant")
        assert link_type == "food"

    def test_swiggy(self):
        _, link_type = classify_url("https://www.swiggy.com/restaurants")
        assert link_type == "food"

    def test_airbnb(self):
        _, link_type = classify_url("https://www.airbnb.com/rooms/123")
        assert link_type == "travel"

    def test_tripadvisor(self):
        _, link_type = classify_url("https://www.tripadvisor.com/Tourism-g123")
        assert link_type == "travel"

    def test_www_normalization(self):
        """Both www and bare domain should classify the same."""
        _, type1 = classify_url("https://www.reddit.com/r/test")
        _, type2 = classify_url("https://reddit.com/r/test")
        assert type1 == type2 == "reddit"

    def test_general_fallback(self):
        _, link_type = classify_url("https://some-random-site.org/page")
        assert link_type == "general"

    def test_url_without_scheme(self):
        domain, link_type = classify_url("youtube.com/watch?v=abc")
        assert link_type == "youtube"
