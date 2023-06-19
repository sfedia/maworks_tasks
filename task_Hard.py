import json
import typing as tp
import re
from enum import Enum
from dataclasses import dataclass, asdict
from selenium import webdriver
from selenium.webdriver.firefox.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.wait import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

"""
Моё решение использует Selenium с драйвером Firefox (geckodriver).
Поэтому помимо selenium из requirements.txt нужно установить Firefox 
"""


metro_prefix = "https://online.metro-cc.ru"
catalog_url = f"{metro_prefix}/category/bakaleya/makaronnye-izdeliya"


@dataclass
class ProductItem:
    """Датакласс для представления карточки товара"""
    sku_id: str # id товара из сайта
    name: str # наименование
    url: str # ссылка на товар
    regular_price: float # регулярная цена
    promo_price: float # промо цена
    brand: str # бренд


class City(Enum):
    """Энумы для представления городов"""
    MOSCOW = 1
    PETERSBURG = 2


# Строковые названия городов для поиска в DOM
city_to_string = {
    City.MOSCOW: "Москва",
    City.PETERSBURG: "Петербург"
}


options = Options()
options.headless = True


def get_goods_for_city(city: City, verbose: bool = True, up_to = 100) -> tp.Dict:
    if verbose:
        print(f"Selecting city ({city_to_string[city]}) and catalog...")
    select_city_and_catalog(city)
    if verbose:
        print(f"Loading additional cards up to {up_to}...")
    expand_product_cards(up_to = up_to)
    if verbose:
        print("Getting brand names to match in product names later...")
    brand_names = get_brand_names()
    brands_pattern = "|".join(brand_names)
    if verbose:
        print("Running JS script to extract raw cards data...")
    raw_data = get_raw_product_cards_data()
    if verbose:
        print("Transforming JS-delivered data to dataclasses...")
    product_items = transform_product_data(raw_data, brands_pattern)
    product_items_to_dict = [
        asdict(item) for item in product_items
    ]
    return product_items_to_dict


def select_city_and_catalog(city: City) -> None:
    show_catalog_button = WebDriverWait(driver, 10).until(
        EC.presence_of_element_located(
            (By.XPATH, "//span[contains(text(),'Смотреть каталог')]/..")
        )
    )
    show_catalog_button.click()
    select_shop_button = WebDriverWait(driver, 10).until(
        EC.presence_of_element_located(
            (By.XPATH, "//span[contains(text(),'Выбрать магазин')]/..")
        )
    )
    select_shop_button.click()
    select_city_button = WebDriverWait(driver, 10).until(
        EC.presence_of_element_located(
            (By.CSS_SELECTOR, ".multiselect__single")
        )
    )
    select_city_button.click()
    city_name = city_to_string[city]
    needed_city_option = WebDriverWait(driver, 10).until(
        EC.presence_of_element_located(
            (By.XPATH, f"//span[contains(@class, 'multiselect__option') and contains(./span/text(), '{city_name}')]")
        )
    )
    needed_city_option.click()
    confirm_city_selection_button = WebDriverWait(driver, 10).until(
        EC.presence_of_element_located(
            (By.XPATH, "//span[contains(text(),'Сохранить')]/..")
        )
    )
    confirm_city_selection_button.click()


def get_brand_names() -> tp.List[str]:
    manufacturer_filters = WebDriverWait(driver, 10).until(
        EC.presence_of_element_located(
            (By.CSS_SELECTOR, ".catalog-filters-manufacturer")
        )
    )
    manufacturer_options = manufacturer_filters.find_elements(By.CSS_SELECTOR, ".app-checkbox__text")
    return [el.get_attribute("innerText").strip("\n ") for el in manufacturer_options]


def expand_product_cards(up_to: int = 100) -> None:
    show_more_button = WebDriverWait(driver, 10).until(
        EC.presence_of_element_located(
            (By.XPATH, "//span[contains(text(),'Показать ещё')]/..")
        )
    )
    product_cards = []
    while len(product_cards) < up_to:
        product_cards = driver.find_elements(By.CSS_SELECTOR, ".catalog-2-level-product-card")
        driver.execute_script("arguments[0].click();", show_more_button)
        driver.implicitly_wait(1)


def price_text_to_float(price_text: str) -> float:
    return float(re.search(r"\d+(?:\.\d+)?", price_text).group(0))


def get_raw_product_cards_data() -> tp.List[tp.Dict[str, tp.Any]]:
    extract_data_script = """
    function getProperties(product) {
        let data_sku = product.getAttribute("data-sku");
        let card_link_element = product.querySelector(".product-card-name__text");
        let old_price_element = product.querySelector(".catalog-2-level-product-card__offline-range-old-price");
        let promo_price = null;
        let default_price_element = product.querySelector(".product-price");
        let default_price = default_price_element.innerText;
        if (old_price_element !== null) {
            promo_price = product.querySelectorAll(".product-price")[1].innerText;
            default_price = old_price_element.innerText;
        } else {
            promo_price = default_price;
        }
        let sold = (product.querySelector(".catalog-2-level-product-card__title-offline") !== null);
        return {
            sku: data_sku,
            name: card_link_element.innerText,
            url: card_link_element.parentNode.getAttribute("href"),
            regular_price: default_price,
            promo_price: promo_price,
            sold: sold
        }
    }
    let products = document.querySelectorAll(".catalog-2-level-product-card");
    return Array.from(products).map(getProperties);
    """
    cards_data = driver.execute_script(extract_data_script)
    return cards_data


def transform_product_data(raw_data: tp.List[tp.Dict[str, tp.Any]], brands_pattern: str) -> tp.List[ProductItem]:
    result_data = []
    for product in raw_data:
        if product["sold"]:
            continue
        data_sku = product["sku"]
        name = product["name"]
        regular_price = price_text_to_float(product["regular_price"])
        promo_price = price_text_to_float(product["promo_price"])
        url = metro_prefix + product["url"]
        brand = None
        brand_occurrences = re.search(brands_pattern, name, re.IGNORECASE)
        if brand_occurrences:
            brand = brand_occurrences.group(0)
        result_data.append(ProductItem(
            sku_id = data_sku,
            name = name,
            url = url,
            regular_price = regular_price,
            promo_price = promo_price,
            brand = brand
        ))
    return result_data


if __name__ == "__main__":
    data = {}
    for city in (City.MOSCOW, City.PETERSBURG):
        driver = webdriver.Firefox(options = options)
        driver.implicitly_wait(3)
        driver.get(catalog_url)
        data[city_to_string[city]] = get_goods_for_city(city)
        driver.close()

    print("Converting data to JSON and writing to file...")
    with open("result.json", "w", encoding = "utf-8") as result:
        result.write(json.dumps(data, indent = 2))
        result.close()
    
    print("Success!")
