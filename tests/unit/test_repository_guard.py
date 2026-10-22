from tools.check_repository_files import check


def test_private_inputs_are_rejected() -> None:
    names = ["data/source.csv", ".env", "notes.docx", "other.csv"]
    assert check(names) == names


def test_synthetic_fixtures_and_env_example_are_allowed() -> None:
    assert check(["tests/fixtures/synthetic.csv", ".env.example"]) == []
