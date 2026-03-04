from __future__ import annotations

import pytest

from xl2times import utils
from xl2times.main import parse_args


def test_parse_args_accepts_force_veda_flag() -> None:
    args = parse_args(["model_dir", "--force-veda"])
    assert args.force_veda is True


def test_is_veda_based_force_requires_syssettings() -> None:
    pattern = r"--force-veda requires exactly one SysSettings\.\*"
    with pytest.raises(ValueError, match=pattern):
        utils.is_veda_based(["VT_Main.xlsx"], force=True)


def test_is_veda_based_force_rejects_multiple_syssettings() -> None:
    with pytest.raises(ValueError, match=r"Multiple detected"):
        utils.is_veda_based(["SysSettings.xlsx", "SysSettings.xlsm"], force=True)
