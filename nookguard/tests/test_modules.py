from nookguard.modules import ModuleRegistry, PromptModule


def _registry() -> ModuleRegistry:
    r = ModuleRegistry()
    r.register(PromptModule(name="style_lifestyle_scene_indoor", version="1.0.0",
                             text="indoor style text", source_note="test"))
    r.register(PromptModule(name="style_lifestyle_scene_outdoor", version="1.0.0",
                             text="outdoor style text", source_note="test"))
    r.register(PromptModule(name="unrelated_module", version="1.0.0",
                             text="unrelated text", source_note="test"))
    return r


def test_register_and_get_roundtrip():
    r = _registry()
    mod = r.get("style_lifestyle_scene_indoor")
    assert mod.text == "indoor style text"


def test_get_unknown_module_raises_keyerror():
    r = _registry()
    try:
        r.get("does_not_exist")
        assert False, "expected KeyError"
    except KeyError:
        pass


def test_module_sha256_is_deterministic():
    mod = PromptModule(name="x", version="1.0.0", text="hello", source_note="t")
    assert mod.module_sha256 == mod.module_sha256


def test_check_compatibility_flags_the_real_incompatible_pair():
    """Direct regression test for the real incident: indoor + outdoor
    lifestyle-scene modules selected together must never compile."""
    r = _registry()
    violations = r.check_compatibility(
        ["style_lifestyle_scene_indoor", "style_lifestyle_scene_outdoor"]
    )
    assert len(violations) == 1
    assert "Incompatible" in violations[0]


def test_check_compatibility_clean_for_single_module():
    r = _registry()
    assert r.check_compatibility(["style_lifestyle_scene_outdoor"]) == []


def test_check_compatibility_flags_unknown_module():
    r = _registry()
    violations = r.check_compatibility(["nonexistent"])
    assert any("Unknown module" in v for v in violations)


def test_compile_modules_raises_on_incompatible_selection():
    r = _registry()
    try:
        r.compile_modules(["style_lifestyle_scene_indoor", "style_lifestyle_scene_outdoor"])
        assert False, "expected ValueError"
    except ValueError:
        pass


def test_compile_modules_concatenates_selected_text():
    r = _registry()
    result = r.compile_modules(["style_lifestyle_scene_outdoor", "unrelated_module"])
    assert "outdoor style text" in result
    assert "unrelated text" in result
