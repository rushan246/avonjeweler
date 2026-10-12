from decimal import Decimal

from django.core.management.base import BaseCommand
from django.utils import timezone

from store.models import Category, MetalRate, Product, ProductImage


class Command(BaseCommand):
    help = "Create a small AVON JEWELER sample catalogue for local development."

    def handle(self, *args, **options):
        categories = {
            name: Category.objects.update_or_create(name=name, defaults={"is_active": True})[0]
            for name in ("Earrings", "Necklaces", "Rings", "Bracelets")
        }
        rates = [
            ("Gold", "22K", "6800.00"),
            ("Gold", "18K", "5560.00"),
            ("Silver", "925", "92.00"),
        ]
        for metal, purity, rate in rates:
            current_rate = MetalRate.objects.filter(metal=metal, purity=purity).order_by("-effective_at").first()
            if current_rate:
                current_rate.price_per_gram = Decimal(rate)
                current_rate.effective_at = timezone.now()
                current_rate.save(update_fields=("price_per_gram", "effective_at"))
            else:
                MetalRate.objects.create(metal=metal, purity=purity, price_per_gram=Decimal(rate), effective_at=timezone.now())
        products = [
            ("Aurelia Gold Hoops", "AV-EAR-001", "Earrings", "Gold", "18K", "fixed", "18900.00", "0.000", "0.00", "Everyday gold hoops with a softly sculpted silhouette and luminous polished finish.", "photo-1535632066927-ab7c9ab60908"),
            ("Solstice Pendant", "AV-NCK-001", "Necklaces", "Gold", "22K", "weight", "0.00", "3.200", "2400.00", "A fine gold pendant inspired by the first light of morning. Crafted to become an heirloom.", "photo-1599643478518-a784e5dc4c8f"),
            ("Mira Diamond Band", "AV-RNG-001", "Rings", "Gold", "18K", "fixed", "32500.00", "0.000", "0.00", "A delicate diamond band, set by hand in warm 18-karat gold.", "photo-1605100804763-247f67b3557e"),
            ("Petal Gold Studs", "AV-EAR-002", "Earrings", "Gold", "22K", "weight", "0.00", "2.100", "1800.00", "Petal-shaped gold studs with an easy elegance that feels just right, every day.", "photo-1617038220319-276d3cfab638"),
            ("Crescent Cuff", "AV-BRC-001", "Bracelets", "Gold", "18K", "fixed", "24600.00", "0.000", "0.00", "A polished sculptural cuff, designed for a confident and effortless statement.", "photo-1611591437281-460bfbe1220a"),
            ("Luna Silver Chain", "AV-NCK-002", "Necklaces", "Silver", "925", "weight", "0.00", "8.000", "450.00", "An understated sterling silver chain with a soft, fluid drape.", "photo-1611652022419-a9419f74343d"),
        ]
        for name, sku, category_name, metal, purity, price_type, fixed_price, weight, making, description, photo in products:
            product, _ = Product.objects.update_or_create(
                sku=sku,
                defaults={
                    "name": name,
                    "category": categories[category_name],
                    "description": description,
                    "metal": metal,
                    "purity": purity,
                    "price_type": price_type,
                    "fixed_price": Decimal(fixed_price),
                    "weight_g": Decimal(weight),
                    "making_charge": Decimal(making),
                    "tax_rate": None,
                    "discount_percent": Decimal("0.00"),
                    "inventory": 12,
                    "is_active": True,
                    "is_featured": sku.endswith("001"),
                },
            )
            ProductImage.objects.update_or_create(
                product=product,
                position=0,
                defaults={
                    "image_url": f"https://images.unsplash.com/{photo}?auto=format&fit=crop&w=1000&q=85",
                    "alt_text": name,
                },
            )
        self.stdout.write(self.style.SUCCESS("Sample AVON JEWELER categories, metal rates, and products are ready."))
