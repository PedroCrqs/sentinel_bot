OPPORTUNITY_SIGNALS = {
    "neighborhood": 10,
    "price": 10,
    "property_type": 5,
    "area_m2": 5,
    "bedrooms": 5,
    "condominium": 15,
    "nearbeach": 10,
}


def neighborhood_match(buyer_neighborhoods, seller_neighborhoods):
    if not buyer_neighborhoods or not seller_neighborhoods:
        return False
    if not isinstance(buyer_neighborhoods, list) or not isinstance(
        seller_neighborhoods, list
    ):
        return False

    from normalizer import NEIGHBORHOOD_PARENT

    SUBBAIRRO_TO_PARENT = {
        raw.upper(): parent for raw, parent in NEIGHBORHOOD_PARENT.items()
    }

    buyer_set = set(buyer_neighborhoods)
    seller_set = set(seller_neighborhoods)

    common = buyer_set & seller_set
    if not common:
        return False

    for subbairro, parent in SUBBAIRRO_TO_PARENT.items():
        buyer_wants_subbairro = subbairro in buyer_set
        seller_has_subbairro = subbairro in seller_set
        match_only_via_parent = (parent in common) and (subbairro not in common)

        if buyer_wants_subbairro and match_only_via_parent and not seller_has_subbairro:
            common.discard(parent)

    return len(common) > 0


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


def nearbeach_match(buyer_nearbeach, seller_nearbeach):
    if buyer_nearbeach and not seller_nearbeach:
        return False
    return True


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

            buyer_cond = buyer.get("condominium")
            seller_cond = seller.get("condominium")

            buyer_nearbeach = buyer.get("nearbeach", False)
            seller_nearbeach = seller.get("nearbeach", False)
            if not nearbeach_match(buyer_nearbeach, seller_nearbeach):
                score = 0
                continue
            if buyer_nearbeach and seller_nearbeach:
                score += OPPORTUNITY_SIGNALS["nearbeach"]
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
