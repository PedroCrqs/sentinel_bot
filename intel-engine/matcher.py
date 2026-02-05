from normalizer import buyers_padronized, sellers_padronized


opportunities = []

OPPORTUNITY_SIGNALS = {
    "neighborhood": 10,
    "price": 10,
    "property_type": 5,
    "bedrooms": 5,
    "area_m2": 5,
}


def range_match(a, b):
    if not a or not b:
        return False

    if a.get("min") is None or b.get("min") is None:
        return False

    return not (a["max"] < b["min"] or b["max"] < a["min"])


def neighborhood_match(a, b):
    if not a or not b:
        return False

    if not isinstance(a, list) or not isinstance(b, list):
        return False

    return len(set(a) & set(b)) > 0


def get_opportunity():

    for buyer in buyers_padronized:
        for seller in sellers_padronized:

            score = 0

            if neighborhood_match(
                buyer.get("neighborhood"), seller.get("neighborhood")
            ):
                score += OPPORTUNITY_SIGNALS["neighborhood"]

            if range_match(buyer.get("price"), seller.get("price")):
                score += OPPORTUNITY_SIGNALS["price"]

            if (
                buyer.get("property_type") is not None
                and seller.get("property_type") is not None
                and buyer["property_type"] == seller["property_type"]
            ):
                score += OPPORTUNITY_SIGNALS["property_type"]

            if range_match(buyer.get("bedrooms"), seller.get("bedrooms")):
                score += OPPORTUNITY_SIGNALS["bedrooms"]
            else:
                score -= 20

            if range_match(buyer.get("area_m2"), seller.get("area_m2")):
                score += OPPORTUNITY_SIGNALS["area_m2"]

            if score > 20:
                opportunities.append({"buyer": buyer, "seller": seller, "score": score})

    print(opportunities)


get_opportunity()
