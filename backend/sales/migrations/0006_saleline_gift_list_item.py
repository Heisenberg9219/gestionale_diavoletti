from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("giftlists", "0001_initial"),
        ("sales", "0005_sale_status_confirmed_index"),
    ]

    operations = [
        migrations.AddField(
            model_name="saleline",
            name="gift_list_item",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="sale_lines",
                to="giftlists.giftlistitem",
            ),
        ),
    ]
