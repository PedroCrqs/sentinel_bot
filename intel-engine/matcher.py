from normalizer import buyers_padronized, sellers_padronized

OPPORTUNITY_SIGNALS = {
    "neighborhood": 10,
    "price": 10,
    "property_type": 5,
    "area_m2": 5,
    "bedrooms": 5,
}


def neighborhood_match(buyer_neighborhoods, seller_neighborhoods):
    if not buyer_neighborhoods or not seller_neighborhoods:
        return False
    if not isinstance(buyer_neighborhoods, list) or not isinstance(
        seller_neighborhoods, list
    ):
        return False
    return len(set(buyer_neighborhoods) & set(seller_neighborhoods)) > 0


def price_match(buyer_price, seller_price):
    if buyer_price is None or seller_price is None:
        return False
    return seller_price <= buyer_price


def bedrooms_match(buyer_bedrooms, seller_bedrooms):
    if buyer_bedrooms is None or seller_bedrooms is None:
        return False
    return seller_bedrooms >= buyer_bedrooms


def area_match(buyer_area, seller_area):
    if buyer_area is None or seller_area is None:
        return False
    return seller_area >= buyer_area


def get_opportunity():
    opportunities = []
    seen_pairs = set()

    for buyer in buyers_padronized:
        for seller in sellers_padronized:

            buyer_id = buyer["original_content"]["message_id"]
            seller_id = seller["original_content"]["message_id"]

            pair_key = (buyer_id, seller_id)

            if pair_key in seen_pairs:
                continue

            seen_pairs.add(pair_key)

            score = 0

            if not neighborhood_match(
                buyer.get("neighborhood"), seller.get("neighborhood")
            ):
                continue

            score += OPPORTUNITY_SIGNALS["neighborhood"]

            if not price_match(buyer.get("price"), seller.get("price")):
                continue

            score += OPPORTUNITY_SIGNALS["price"]

            if not bedrooms_match(buyer.get("bedrooms"), seller.get("bedrooms")):
                continue

            score += OPPORTUNITY_SIGNALS["bedrooms"]

            if buyer.get("property_type") == seller.get("property_type"):
                score += OPPORTUNITY_SIGNALS["property_type"]

            if area_match(buyer.get("area_m2"), seller.get("area_m2")):
                score += OPPORTUNITY_SIGNALS["area_m2"]

            opportunities.append({"buyer": buyer, "seller": seller, "score": score})

    return opportunities


opportunities = get_opportunity()
for opp in opportunities:
    print(f"\n{'='*80}")
    print(f"SCORE: {opp['score']}")
    print(f"\nCOMPRADOR:")
    print(f"  Mensagem: {opp['buyer']['raw_text']}...")
    print(f"  Bairro: {opp['buyer']['neighborhood']}")
    print(f"  Preço máx: {opp['buyer']['price']}")
    print(f"  Quartos mín: {opp['buyer']['bedrooms']}")
    print(f"  Área mín: {opp['buyer']['area_m2']}")
    print(f"\nVENDEDOR:")
    print(f"  Mensagem: {opp['seller']['raw_text']}...")
    print(f"  Bairro: {opp['seller']['neighborhood']}")
    print(f"  Preço: {opp['seller']['price']}")
    print(f"  Quartos: {opp['seller']['bedrooms']}")
    print(f"  Área: {opp['seller']['area_m2']}")
    print(f"{'='*80}")
