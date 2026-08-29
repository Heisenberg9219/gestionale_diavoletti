from django.db import migrations


SCALES = [
    ("NEWBORN", "Neonato", "AGE"),
    ("CHILD", "Bambino", "AGE"),
    ("TEEN", "Ragazzo", "AGE"),
    ("ADULT", "Adulto", "ALPHA"),
    ("ONE_SIZE", "Taglia unica", "ONE_SIZE"),
]

NEWBORN_SIZES = [
    ("0M", "0M", 0, 0),
    ("1M", "1M", 1, 2),
    ("3M", "3M", 3, 5),
    ("6M", "6M", 6, 8),
    ("9M", "9M", 9, 11),
    ("12M", "12M", 12, 17),
    ("18M", "18M", 18, 23),
    ("24M", "24M", 24, 35),
    ("36M", "36M", 36, 47),
    ("0-3M", "0-3 mesi", 0, 2),
    ("3-6M", "3-6 mesi", 3, 5),
    ("6-9M", "6-9 mesi", 6, 8),
    ("9-12M", "9-12 mesi", 9, 11),
    ("12-18M", "12-18 mesi", 12, 17),
    ("18-24M", "18-24 mesi", 18, 23),
    ("24-36M", "24-36 mesi", 24, 35),
]

CHILD_SINGLE_SIZES = [
    (f"{year}A", f"{year} anni", year * 12, year * 12 + 11)
    for year in range(2, 11)
]

CHILD_RANGE_SIZES = [
    (
        f"{year}-{year + 1}A",
        f"{year}-{year + 1} anni",
        year * 12,
        (year + 1) * 12 - 1,
    )
    for year in range(2, 10)
]

TEEN_SINGLE_SIZES = [
    (f"{year}A", f"{year} anni", year * 12, year * 12 + 11)
    for year in range(11, 17)
]

TEEN_RANGE_SIZES = [
    (
        f"{year}-{year + 1}A",
        f"{year}-{year + 1} anni",
        year * 12,
        (year + 1) * 12 - 1,
    )
    for year in range(11, 16)
]

ADULT_SIZES = [
    ("S", "S", None, None),
    ("M", "M", None, None),
    ("L", "L", None, None),
    ("XL", "XL", None, None),
    ("XXL", "XXL", None, None),
    ("XXXL", "XXXL", None, None),
]

ONE_SIZE = [
    ("TU", "Taglia unica", None, None),
]


def create_sizes(Size, scale, definitions, starting_order=10):
    for index, (code, label, min_age, max_age) in enumerate(
        definitions,
        start=1,
    ):
        Size.objects.get_or_create(
            size_scale=scale,
            code=code,
            defaults={
                "label": label,
                "min_age_months": min_age,
                "max_age_months": max_age,
                "display_order": starting_order + index,
                "is_active": True,
            },
        )


def seed_initial_sizes(apps, schema_editor):
    SizeScale = apps.get_model("catalog", "SizeScale")
    Size = apps.get_model("catalog", "Size")

    scales = {}

    for code, name, scale_type in SCALES:
        scale, _ = SizeScale.objects.get_or_create(
            code=code,
            defaults={
                "name": name,
                "scale_type": scale_type,
                "is_active": True,
            },
        )
        scales[code] = scale

    create_sizes(
        Size,
        scales["NEWBORN"],
        NEWBORN_SIZES,
    )
    create_sizes(
        Size,
        scales["CHILD"],
        CHILD_SINGLE_SIZES,
    )
    create_sizes(
        Size,
        scales["CHILD"],
        CHILD_RANGE_SIZES,
        starting_order=100,
    )
    create_sizes(
        Size,
        scales["TEEN"],
        TEEN_SINGLE_SIZES,
    )
    create_sizes(
        Size,
        scales["TEEN"],
        TEEN_RANGE_SIZES,
        starting_order=100,
    )
    create_sizes(
        Size,
        scales["ADULT"],
        ADULT_SIZES,
    )
    create_sizes(
        Size,
        scales["ONE_SIZE"],
        ONE_SIZE,
    )


def remove_initial_sizes(apps, schema_editor):
    SizeScale = apps.get_model("catalog", "SizeScale")
    Size = apps.get_model("catalog", "Size")

    scale_codes = [code for code, _, _ in SCALES]

    Size.objects.filter(
        size_scale__code__in=scale_codes
    ).delete()

    SizeScale.objects.filter(
        code__in=scale_codes
    ).delete()


class Migration(migrations.Migration):
    dependencies = [
        ("catalog", "0001_initial"),
    ]

    operations = [
        migrations.RunPython(
            seed_initial_sizes,
            remove_initial_sizes,
        ),
    ]