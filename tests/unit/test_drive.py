from nf_core.drive import find_my_drive


def test_find_my_drive_mac(tmp_path):
    assert find_my_drive(tmp_path, "darwin") == []
    b = tmp_path / "Library" / "CloudStorage" / "GoogleDrive-b@y.com" / "My Drive"
    a = tmp_path / "Library" / "CloudStorage" / "GoogleDrive-a@x.com" / "My Drive"
    for d in (b, a):
        d.mkdir(parents=True)
    (tmp_path / "Library" / "CloudStorage" / "OneDrive-Personal").mkdir()
    assert find_my_drive(tmp_path, "darwin") == [a, b]


def test_find_my_drive_windows(tmp_path):
    home = tmp_path / "home"
    e, g = tmp_path / "E", tmp_path / "G"
    e.mkdir()
    (g / "My Drive").mkdir(parents=True)
    (home / "My Drive").mkdir(parents=True)
    assert find_my_drive(home, "win32", win_roots=[e, g]) == [g / "My Drive", home / "My Drive"]
    assert find_my_drive(tmp_path / "nobody", "win32", win_roots=[e]) == []

