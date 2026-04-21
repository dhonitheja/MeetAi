import os

import pytest

os.environ["PERSONA_MACHINE_ID"] = "test-machine"
os.environ["PERSONA_USER_SALT"] = "test-salt-1234"

from backend.persona.persona_manager import Persona, PersonaManager


def make_persona(**kwargs) -> Persona:
    defaults = dict(
        display_name="Test Persona",
        voice_id="a1b2c3d4e5f6a1b2",
        face_id="b2c3d4e5f6a1b2c3",
        system_prompt="Be concise.",
    )
    defaults.update(kwargs)
    return Persona(**defaults)


def test_save_and_load_roundtrip(tmp_path, monkeypatch):
    monkeypatch.setattr("backend.persona.persona_manager.PERSONAS_DIR", tmp_path)
    mgr = PersonaManager()
    p = make_persona()
    mgr.save(p)
    loaded = mgr.load(p.persona_id)
    assert loaded.display_name == p.display_name
    assert loaded.voice_id == p.voice_id
    assert loaded.face_id == p.face_id
    assert loaded.system_prompt == p.system_prompt


def test_invalid_persona_id_rejected():
    mgr = PersonaManager()
    with pytest.raises(ValueError):
        mgr.load("../../etc/passwd")
    with pytest.raises(ValueError):
        mgr.delete("not-a-hex-id\n")


def test_invalid_voice_id_rejected():
    with pytest.raises(ValueError):
        make_persona(voice_id="not-hex")


def test_invalid_face_id_rejected():
    with pytest.raises(ValueError):
        make_persona(face_id="toolongid12345678901234")


def test_no_eval_or_pickle_in_source():
    import inspect
    from backend.persona import persona_manager as mod

    src = inspect.getsource(mod)
    assert "eval(" not in src, "CRITICAL: eval() found in persona_manager"
    assert "pickle" not in src, "CRITICAL: pickle found in persona_manager"
    assert "json.loads" in src, "json.loads must be used for deserialization"


def test_key_never_written_to_disk(tmp_path, monkeypatch):
    monkeypatch.setattr("backend.persona.persona_manager.PERSONAS_DIR", tmp_path)
    mgr = PersonaManager()
    p = make_persona()
    mgr.save(p)
    saved = (tmp_path / f"{p.persona_id}.json").read_text()
    assert "PERSONA_MACHINE_ID" not in saved
    assert "PERSONA_USER_SALT" not in saved


def test_missing_env_raises(monkeypatch):
    monkeypatch.delenv("PERSONA_MACHINE_ID", raising=False)
    monkeypatch.delenv("PERSONA_USER_SALT", raising=False)
    mgr = PersonaManager()
    with pytest.raises(EnvironmentError):
        mgr._derive_key(b"fakesalt1234abcd")
