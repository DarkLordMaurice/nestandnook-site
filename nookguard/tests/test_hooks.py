"""Pure unit tests for nookguard/hooks.py's PreToolUse policy logic (Commit
11, Appendix G hooks H001-H004, H008, H009). No live Claude Code hook
invocation is exercised here -- that's the one genuinely unverifiable-in-
session part of this commit (same standing caveat as the Anthropic/HF live
network calls in Commits 5/7/10) -- but every rule's actual decision logic
is real and thoroughly covered, matching the project's "test the mechanism
you can test for real" discipline."""

from __future__ import annotations

from pathlib import Path

from nookguard.hooks import (
    check_bash,
    check_bash_blanket_git_add,
    check_bash_generation_endpoint,
    check_bash_production_branch,
    check_content_lint_on_edit,
    check_write_edit_protected_path,
    check_write_to_published_media,
    evaluate_pretooluse,
)

# ---- H001: protected store path ----

def test_h001_denies_write_into_store():
    reason = check_write_edit_protected_path({"file_path": "/proj/nookguard_store/specs/x.json"})
    assert reason is not None
    assert "H001" in reason


def test_h001_denies_edit_into_store_with_backslashes():
    reason = check_write_edit_protected_path({"file_path": r"C:\proj\nookguard_store\attempts\x.json"})
    assert reason is not None


def test_h001_allows_write_outside_store():
    reason = check_write_edit_protected_path({"file_path": "/proj/site/src/content/blog/post.md"})
    assert reason is None


def test_h001_does_not_false_positive_on_similar_dirname():
    """'nookguard' (the package) and 'nookguard_store' (the protected data
    dir) are different path segments -- editing nookguard/hooks.py itself
    must not be blocked."""
    reason = check_write_edit_protected_path({"file_path": "/proj/site/nookguard/hooks.py"})
    assert reason is None


# ---- H002: direct generation-endpoint calls ----

def test_h002_denies_gradio_client_predict_call():
    reason = check_bash_generation_endpoint(
        'python -c "from gradio_client import Client; Client(\'x\').predict(prompt)"')
    assert reason is not None
    assert "H002" in reason


def test_h002_denies_gradio_client_submit_call():
    reason = check_bash_generation_endpoint(
        'python -c "from gradio_client import Client; Client(\'x\').submit(prompt)"')
    assert reason is not None


def test_h002_denies_direct_anthropic_messages_call():
    reason = check_bash_generation_endpoint(
        'python -c "import anthropic; c = anthropic.Anthropic(); c.messages.create(model=1)"')
    assert reason is not None


def test_h002_denies_curl_to_hf_space():
    reason = check_bash_generation_endpoint("curl https://huggingface.co/spaces/Tongyi-MAI/Z-Image-Turbo")
    assert reason is not None


def test_h002_allows_bare_pip_install_of_gradio_client():
    """A package name appearing alone (install/inspect) is not an
    invocation -- must never be false-flagged."""
    reason = check_bash_generation_endpoint("pip install gradio_client --break-system-packages")
    assert reason is None


def test_h002_allows_bare_mention_of_anthropic_package():
    reason = check_bash_generation_endpoint("pip show anthropic")
    assert reason is None


def test_h002_allows_when_mediactl_present():
    reason = check_bash_generation_endpoint(
        "mediactl generate --adapter huggingface --spec x --prompt y  # gradio_client under the hood, .predict(")
    assert reason is None


def test_h002_allows_when_pytest_present():
    reason = check_bash_generation_endpoint(
        "pytest nookguard/tests/test_adapters_huggingface.py -k gradio_client_predict")
    assert reason is None


# ---- H003: blanket git staging ----

def test_h003_denies_git_add_dash_A():
    assert check_bash_blanket_git_add("git add -A") is not None


def test_h003_denies_git_add_dash_dash_all():
    assert check_bash_blanket_git_add("git add --all") is not None


def test_h003_denies_git_add_dot_alone():
    assert check_bash_blanket_git_add("git add .") is not None


def test_h003_denies_git_add_dot_chained():
    assert check_bash_blanket_git_add("git add . && git commit -m x") is not None


def test_h003_denies_git_add_dot_semicolon():
    assert check_bash_blanket_git_add("git add .; git commit -m x") is not None


def test_h003_allows_specific_file_staging():
    assert check_bash_blanket_git_add("git add nookguard/hooks.py nookguard/cli.py") is None


def test_h003_does_not_false_positive_on_dotted_path():
    """A real regression this rule must avoid: staging a specific file whose
    name/path happens to contain a dot must not be mistaken for 'git add .'"""
    assert check_bash_blanket_git_add("git add .github/workflows/nookguard-ci.yml") is None
    assert check_bash_blanket_git_add("git add docs/nookguard/BUILD-LOG.md") is None


# ---- H004: production branch ----

def test_h004_denies_checkout_production():
    assert check_bash_production_branch("git checkout production") is not None


def test_h004_denies_push_to_production():
    assert check_bash_production_branch("git push origin production") is not None


def test_h004_denies_merge_production():
    assert check_bash_production_branch("git merge production") is not None


def test_h004_denies_branch_delete_production():
    assert check_bash_production_branch("git branch -d production") is not None


def test_h004_allows_push_to_main():
    assert check_bash_production_branch("git push origin main") is None


def test_h004_allows_unrelated_mention_of_word_production():
    """A non-mutating command that merely mentions the word (e.g. grepping
    logs) is not what this hook is for."""
    assert check_bash_production_branch("git log --all | grep production") is None


# ---- check_bash dispatch ----

def test_check_bash_runs_all_rules_git_add_wins_first():
    reason = check_bash("git add -A && git push origin production")
    assert reason is not None
    assert "H003" in reason  # staging check runs before branch check


def test_check_bash_clean_command_allowed():
    assert check_bash("npm run build") is None


# ---- H008: any write to published media (strengthened Commit 21 -- see
# hooks.py's check_write_to_published_media docstring: this used to only
# deny an OVERWRITE of an existing file; public-media containment closed
# the gap where a brand-new file at a published path sailed through) ----

def test_h008_denies_overwrite_of_existing_media_file(tmp_path):
    media_dir = tmp_path / "public" / "winnie"
    media_dir.mkdir(parents=True)
    existing = media_dir / "hero.jpg"
    existing.write_bytes(b"fake-jpeg-bytes")

    reason = check_write_to_published_media({"file_path": str(existing)}, tmp_path)
    assert reason is not None
    assert "H008" in reason


def test_h008_denies_write_of_new_media_file(tmp_path):
    """Commit 21: a NEW file at a published path is exactly as much a
    containment bypass as overwriting one -- this is the specific gap this
    commit closed (see hooks.py's check_write_to_published_media
    docstring, and requirement 1's 'block all NEW and modified public
    media')."""
    media_dir = tmp_path / "public" / "winnie"
    media_dir.mkdir(parents=True)
    new_path = media_dir / "brand-new.jpg"  # does not exist yet

    reason = check_write_to_published_media({"file_path": str(new_path)}, tmp_path)
    assert reason is not None
    assert "H008" in reason
    assert "new file" in reason


def test_h008_ignores_non_media_extension(tmp_path):
    media_dir = tmp_path / "public" / "winnie"
    media_dir.mkdir(parents=True)
    existing = media_dir / "notes.txt"
    existing.write_text("hi")

    reason = check_write_to_published_media({"file_path": str(existing)}, tmp_path)
    assert reason is None


def test_h008_ignores_media_outside_published_dirs(tmp_path):
    other_dir = tmp_path / "scratch"
    other_dir.mkdir()
    existing = other_dir / "hero.jpg"
    existing.write_bytes(b"x")

    reason = check_write_to_published_media({"file_path": str(existing)}, tmp_path)
    assert reason is None


# ---- H009: content-lint on hypothetical post-edit content ----

_VALID_STRIP = '<div class="photo-strip">\n<figure></figure><figure></figure><figure></figure>\n</div>'
_VALID_SINGLE = '<div class="photo-single">\n<figure></figure>\n</div>'
_VALID_BODY = f"Some intro text.\n\n{_VALID_STRIP}\n\nMore text.\n\n{_VALID_SINGLE}\n"
_FRONTMATTER = '---\ncategory: "Life outside the nook"\n---\n'


def _write_real_off_the_clock_file(tmp_path: Path) -> Path:
    p = tmp_path / "a-real-post.md"
    p.write_text(_FRONTMATTER + _VALID_BODY, encoding="utf-8")
    return p


def test_h009_write_of_bad_new_file_is_denied(tmp_path):
    # A photo-strip block with 2 images instead of the required 3.
    broken_strip = '<div class="photo-strip">\n<figure></figure><figure></figure>\n</div>'
    bad_content = _FRONTMATTER + f"Text.\n\n{broken_strip}\n"
    reason = check_content_lint_on_edit("Write", {"file_path": "new-post.md", "content": bad_content}, tmp_path)
    assert reason is not None
    assert "H009" in reason


def test_h009_write_of_clean_new_file_is_allowed(tmp_path):
    reason = check_content_lint_on_edit(
        "Write", {"file_path": "new-post.md", "content": _FRONTMATTER + _VALID_BODY}, tmp_path)
    assert reason is None


def test_h009_edit_that_breaks_photo_strip_count_is_denied(tmp_path):
    real_file = _write_real_off_the_clock_file(tmp_path)
    reason = check_content_lint_on_edit(
        "Edit",
        {
            "file_path": str(real_file),
            "old_string": _VALID_STRIP,
            "new_string": '<div class="photo-strip">\n<figure></figure><figure></figure>\n</div>',
        },
        tmp_path,
    )
    assert reason is not None
    assert "H009" in reason


def test_h009_edit_that_preserves_compliant_layout_is_allowed(tmp_path):
    real_file = _write_real_off_the_clock_file(tmp_path)
    reason = check_content_lint_on_edit(
        "Edit",
        {"file_path": str(real_file), "old_string": "Some intro text.", "new_string": "A different intro."},
        tmp_path,
    )
    assert reason is None


def test_h009_ignores_non_markdown_files(tmp_path):
    reason = check_content_lint_on_edit("Write", {"file_path": "notes.txt", "content": "hi"}, tmp_path)
    assert reason is None


def test_h009_ignores_files_outside_off_the_clock_categories(tmp_path):
    guides_content = '---\ncategory: "Desk fixes"\n---\n\nSome guide content.\n'
    reason = check_content_lint_on_edit("Write", {"file_path": "guide.md", "content": guides_content}, tmp_path)
    assert reason is None


def test_h009_edit_on_nonexistent_file_is_not_this_hooks_concern(tmp_path):
    reason = check_content_lint_on_edit(
        "Edit", {"file_path": str(tmp_path / "does-not-exist.md"), "old_string": "a", "new_string": "b"}, tmp_path)
    assert reason is None


# ---- evaluate_pretooluse dispatch ----

def test_evaluate_dispatches_bash_to_bash_rules(tmp_path):
    reason = evaluate_pretooluse("Bash", {"command": "git add -A"}, tmp_path)
    assert reason is not None and "H003" in reason


def test_evaluate_dispatches_write_to_protected_path_check(tmp_path):
    reason = evaluate_pretooluse(
        "Write", {"file_path": str(tmp_path / "nookguard_store" / "x.json"), "content": "{}"}, tmp_path)
    assert reason is not None and "H001" in reason


def test_evaluate_ignores_unrelated_tool_names(tmp_path):
    assert evaluate_pretooluse("Read", {"file_path": "anything"}, tmp_path) is None
    assert evaluate_pretooluse("Grep", {"pattern": "x"}, tmp_path) is None


def test_evaluate_allows_clean_bash_and_clean_write(tmp_path):
    assert evaluate_pretooluse("Bash", {"command": "npm run build"}, tmp_path) is None
    assert evaluate_pretooluse(
        "Write", {"file_path": str(tmp_path / "src" / "components" / "Foo.astro"), "content": "<div/>"}, tmp_path,
    ) is None
