# JSON 병합 로직 구현 설명 정리

## 1. 상황 정의

세로로 긴 상품 상세페이지 이미지를 분할하여 VL 모델로 처리한 후, 각 분할
이미지에서 다음과 같은 JSON 결과를 받았다고 가정한다.

``` python
parts = [
    {
        "product_name": "프리미엄 코튼 오버핏 셔츠",
        "brand": "ABC",
        "category": None,
        "material": None,
        "origin_country": None,
        "color": None,
        "size": None,
        "description": None
    },
    {
        "product_name": None,
        "brand": None,
        "category": None,
        "material": "면 100%",
        "origin_country": "대한민국",
        "color": ["화이트", "블랙"],
        "size": ["M", "L"],
        "description": None
    },
    {
        "product_name": None,
        "brand": None,
        "category": None,
        "material": None,
        "origin_country": None,
        "color": None,
        "size": None,
        "description": "오버핏 실루엣의 데일리 셔츠"
    }
]
```

이 여러 개의 JSON을 하나의 최종 상품 JSON으로 병합해야 한다.

------------------------------------------------------------------------

# 2. 병합 기본 원칙

-   null이 아닌 값 우선
-   배열(color, size)은 합집합
-   충돌 시 보수적 처리
-   product_name은 가장 긴 값 선택
-   description은 합치되 길이 제한 적용

------------------------------------------------------------------------

# 3. 병합 함수 구현 예시 (Python)

``` python
def merge_product_json(parts):
    final = {
        "product_name": None,
        "brand": None,
        "category": None,
        "material": None,
        "origin_country": None,
        "color": [],
        "size": [],
        "description": None,
        "meta": {
            "source_parts": len(parts),
            "conflict": {
                "brand": False,
                "material": False,
                "origin_country": False
            },
            "null_ratio": 0.0
        }
    }

    # product_name
    names = [p["product_name"] for p in parts if p.get("product_name")]
    if names:
        final["product_name"] = max(names, key=len)

    # brand
    brands = list(set(p["brand"] for p in parts if p.get("brand")))
    if len(brands) == 1:
        final["brand"] = brands[0]
    elif len(brands) > 1:
        final["meta"]["conflict"]["brand"] = True

    # material
    materials = [p["material"] for p in parts if p.get("material")]
    if materials:
        final["material"] = max(materials, key=len)

    # origin_country
    origins = list(set(p["origin_country"] for p in parts if p.get("origin_country")))
    if len(origins) == 1:
        final["origin_country"] = origins[0]
    elif len(origins) > 1:
        final["meta"]["conflict"]["origin_country"] = True

    # color
    colors = []
    for p in parts:
        if p.get("color"):
            colors.extend(p["color"])
    final["color"] = list(set(colors)) if colors else None

    # size
    sizes = []
    for p in parts:
        if p.get("size"):
            sizes.extend(p["size"])
    final["size"] = list(set(sizes)) if sizes else None

    # description
    descriptions = [p["description"] for p in parts if p.get("description")]
    if descriptions:
        combined = " ".join(set(descriptions))
        final["description"] = combined[:300]

    # null_ratio 계산
    total_fields = 8
    null_count = sum(
        1 for k in final if k != "meta" and not final[k]
    )
    final["meta"]["null_ratio"] = null_count / total_fields

    return final
```

------------------------------------------------------------------------

# 4. 핵심 이해 포인트

병합은 LLM처럼 "추론"하는 것이 아니라, 정해진 규칙으로 값을 선택하고
충돌을 처리하는 과정이다.

-   충돌은 flag로 남긴다
-   정보는 최대한 보수적으로 선택한다
-   재현 가능한 결정적 로직을 유지한다

------------------------------------------------------------------------

# 5. 운영 시 확장 가능 영역

-   값 정규화 (국가명, 색상명 표준화)
-   카테고리별 병합 전략 분기
-   conflict 발생 시 재검증 로직 추가
-   품질 점수 기반 자동 재시도 시스템

------------------------------------------------------------------------

문서 끝.
