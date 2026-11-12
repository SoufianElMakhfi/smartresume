import launcher


def test_server_binds_locally_without_dev_toolbar():
    args = launcher.server_args(8600)
    opt = dict(zip(args[3::2], args[4::2]))
    assert opt["--server.address"] == "127.0.0.1" and opt["--server.port"] == "8600"
    assert opt["--client.toolbarMode"] == "viewer"          # kein „Deploy“-Knopf
    assert opt["--global.developmentMode"] == "false"


def test_server_command_runs_launcher_in_server_mode():
    cmd = launcher._server_command()
    assert cmd[-1] == "--server" and cmd[-2].endswith("launcher.py")
