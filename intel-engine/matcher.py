OPPORTUNITY_SIGNALS = {
    "neighborhood": 10,
    "price": 10,
    "property_type": 5,
    "area_m2": 5,
    "bedrooms": 5,
    "condominium": 15,
    "nearbeach": 10,
    "seafront": 10,
    "sun_type": 5,
    "parking_spots": 5,
}


def neighborhood_match(buyer, seller):
    buyer_neighborhoods = buyer.get("neighborhood")
    seller_neighborhoods = seller.get("neighborhood")

    if not buyer_neighborhoods or not seller_neighborhoods:
        return False
    if not isinstance(buyer_neighborhoods, list) or not isinstance(
        seller_neighborhoods, list
    ):
        return False

    buyer_sub = buyer.get("sub_neighborhood")
    seller_sub = seller.get("sub_neighborhood")

    # Regra core: se o comprador pediu um sub-bairro específico,
    # o vendedor DEVE ter exatamente esse sub-bairro.
    if buyer_sub:
        return seller_sub == buyer_sub

    # Comprador sem sub-bairro: match normal por interseção de neighborhoods.
    # Vendedor em sub-bairro pode ser oferecido a comprador que quer o parent.
    buyer_set = set(buyer_neighborhoods)
    seller_set = set(seller_neighborhoods)
    return bool(buyer_set & seller_set)


def price_match(buyer_price, seller_price):
    if buyer_price is None or seller_price is None:
        return False
    upper_limit = buyer_price + 50_000
    lower_limit = buyer_price * 0.80
    return lower_limit <= seller_price <= upper_limit


def bedrooms_match(buyer_bedrooms, seller_bedrooms):
    if buyer_bedrooms is None or seller_bedrooms is None:
        return False
    return seller_bedrooms >= buyer_bedrooms


def area_match(buyer_area, seller_area):
    if buyer_area is None or seller_area is None:
        return False
    return seller_area >= buyer_area


def parking_spots_match(buyer_parking, seller_parking):
    if seller_parking is None:
        return False
    return seller_parking >= buyer_parking


def nearbeach_match(buyer_nearbeach, seller_nearbeach):
    if buyer_nearbeach and not seller_nearbeach:
        return False
    return True


def seafront_match(buyer_seafront, seller_seafront):
    if buyer_seafront and not seller_seafront:
        return False
    return True


def sun_type_match(buyer_sun_type, seller_sun_type):
    if not buyer_sun_type or not seller_sun_type:
        return False
    return buyer_sun_type == seller_sun_type


def condominium_match(buyer_condominium, seller_condominium):
    if not buyer_condominium or not seller_condominium:
        return False
    seller_lower = seller_condominium.lower()
    if isinstance(buyer_condominium, list):
        return any(cond.lower() == seller_lower for cond in buyer_condominium)
    return buyer_condominium.lower() == seller_lower


def get_opportunity(sellers_padronized, buyers_padronized):
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

            if not neighborhood_match(buyer, seller):
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

            buyer_area = buyer.get("area_m2")
            if buyer_area is not None:
                if not area_match(buyer_area, seller.get("area_m2")):
                    continue
                score += OPPORTUNITY_SIGNALS["area_m2"]

            buyer_parking = buyer.get("parking_spots")
            if buyer_parking is not None:
                if not parking_spots_match(buyer_parking, seller.get("parking_spots")):
                    continue
                score += OPPORTUNITY_SIGNALS["parking_spots"]

            buyer_cond = buyer.get("condominium")
            seller_cond = seller.get("condominium")

            buyer_nearbeach = buyer.get("nearbeach", False)
            seller_nearbeach = seller.get("nearbeach", False)
            if not nearbeach_match(buyer_nearbeach, seller_nearbeach):
                score = 0
                continue
            if buyer_nearbeach and seller_nearbeach:
                score += OPPORTUNITY_SIGNALS["nearbeach"]

            buyer_seafront = buyer.get("seafront", False)
            seller_seafront = seller.get("seafront", False)
            if not seafront_match(buyer_seafront, seller_seafront):
                continue
            if buyer_seafront and seller_seafront:
                score += OPPORTUNITY_SIGNALS["seafront"]

            buyer_sun_type = buyer.get("sun_type")
            seller_sun_type = seller.get("sun_type")
            if buyer_sun_type:
                if sun_type_match(buyer_sun_type, seller_sun_type):
                    score += OPPORTUNITY_SIGNALS["sun_type"]

            if buyer_cond:
                if not condominium_match(buyer_cond, seller_cond):
                    continue
                score += OPPORTUNITY_SIGNALS["condominium"]
            elif seller_cond:
                score += OPPORTUNITY_SIGNALS["condominium"] // 2

            opportunities.append({"buyer": buyer, "seller": seller, "score": score})

    return sorted(opportunities, key=lambda x: x["score"], reverse=True)


# opportunities = get_opportunity()
# for opp in opportunities:
#     print(f"\n{'='*80}")
#     print(f"SCORE: {opp['score']}")
#     print(f"\nCOMPRADOR:")
#     print(f"  Mensagem: {opp['buyer']['raw_text']}...")
#     print(f"  Bairro: {opp['buyer']['neighborhood']}")
#     print(f"  Preço máx: {opp['buyer']['price']}")
#     print(f"  Quartos mín: {opp['buyer']['bedrooms']}")
#     print(f"  Área mín: {opp['buyer']['area_m2']}")
#     print(f"\nVENDEDOR:")
#     print(f"  Mensagem: {opp['seller']['raw_text']}...")
#     print(f"  Bairro: {opp['seller']['neighborhood']}")
#     print(f"  Preço: {opp['seller']['price']}")
#     print(f"  Quartos: {opp['seller']['bedrooms']}")
#     print(f"  Área: {opp['seller']['area_m2']}")
#     print(f"{'='*80}")
