from typing import cast

import pandas as pd

from xl2times.datatypes import Config, EmbeddedXlTable, Tag, TimesModel
from xl2times.transforms import process_time_periods


def _embedded_table(tag: Tag, rows: list[dict]) -> EmbeddedXlTable:
    return EmbeddedXlTable(
        tag=tag.value,
        uc_sets={},
        sheetname="TimePeriods",
        range="A1",
        filename="SysSettings.xlsx",
        dataframe=pd.DataFrame(rows),
    )


def test_process_time_periods_accepts_milestone_only_table_without_endyear():
    tables = [
        _embedded_table(Tag.start_year, [{"value": 2025}]),
        _embedded_table(
            Tag.milestoneyears,
            [
                {"type": "milestoneyear", "pathway_2025_2035": 2025},
                {"type": "milestoneyear", "pathway_2025_2035": 2030},
                {"type": "milestoneyear", "pathway_2025_2035": 2035},
            ],
        ),
    ]
    model = TimesModel()

    process_time_periods(cast(Config, object()), tables, model)

    assert model.start_year == 2025
    assert model.time_periods.to_dict("records") == [
        {"d": 5, "b": 2025, "e": 2029, "m": 2025, "year": 2025},
        {"d": 5, "b": 2030, "e": 2034, "m": 2030, "year": 2030},
        {"d": 1, "b": 2035, "e": 2035, "m": 2035, "year": 2035},
    ]
