"""Test lõi kho.py — chạy: python -m pytest tools/test_kho.py -q"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import kho  # noqa: E402

UID = "1735325143133161461"


def test_tach_uid_cac_dang_link():
    assert kho.tach_uid(f"https://shop.tiktok.com/vn/pdp/{UID}?source=abc") == UID
    assert kho.tach_uid(f"https://shop.tiktok.com/view/product/{UID}?region=VN") == UID
    assert kho.tach_uid(f"https://www.tiktok.com/view/product/{UID}") == UID
    assert kho.tach_uid(f"https://echotik.live/products/{UID}") == UID
    assert kho.tach_uid(UID) == UID
    assert kho.tach_uid("https://vt.tiktok.com/ZS9AR1U4aqHLh/") is None
    assert kho.tach_uid("linh tinh") is None


def test_link_chuan():
    assert kho.link_chuan(UID) == f"https://shop.tiktok.com/vn/pdp/{UID}"


def test_kiem_captions():
    tot = "Áo khoác lông cừu cho bé mặc đi học #aokhoac #aokhoactreem #balabala #dotreem #aolongcuu"
    assert kho.kiem_captions([tot]) == []
    loi = kho.kiem_captions(["thiếu hashtag #a #b", "x" * 151 + " #a #b #c #d #e", "1. " + tot])
    assert any("dòng 1" in e and "hashtag" in e for e in loi)
    assert any("dòng 2" in e and "150" in e for e in loi)
    assert any("dòng 3" in e and "số thứ tự" in e for e in loi)


def test_nhan_trang_thai():
    assert kho.nhan_trang_thai({}) == "cho"
    assert kho.nhan_trang_thai({"da_phan_tich": True}) == "da_phan_tich"
    assert kho.nhan_trang_thai({"da_phan_tich": True, "da_quay_oneshot": {"xong": True}}) == "da_quay"
    assert kho.nhan_trang_thai({"da_phan_tich": True, "da_quay_review": {"xong": True}}) == "da_quay"
    assert kho.nhan_trang_thai({"da_quay_review": {"xong": True}, "da_lam_video": {"xong": True}}) == "da_lam_video"
    # dữ liệu cũ (1 nút "da_quay") vẫn tính là đã quay review
    assert kho.nhan_trang_thai({"da_quay": {"xong": True}}) == "da_quay"


def test_quay_hai_loai():
    i = kho.info_moi("1", "1", "x")
    assert i["da_quay_oneshot"]["xong"] is False and i["da_quay_review"]["xong"] is False
    kho.danh_dau_quay(i, "oneshot", True, "Lan")
    assert i["da_quay_oneshot"]["xong"] and i["da_quay_oneshot"]["boi"] == "Lan"
    assert not i["da_quay_review"]["xong"]
    assert kho.da_quay(i, "oneshot") and not kho.da_quay(i, "review")
    assert kho.da_quay({"da_quay": {"xong": True}}, "review")


def test_doc_du_lieu_pdp(tmp_path):
    (tmp_path / "du_lieu_tho").mkdir()
    (tmp_path / "du_lieu_tho" / "sp_pdp.json").write_text(json.dumps({
        "product_id": UID, "ten": "Router 4G", "gia": "199.000₫", "seller_name": "Homewise",
        "anh": {"bia": ["https://x/1.jpg"]}}), encoding="utf-8")
    (tmp_path / "du_lieu_tho" / "usp.json").write_text(json.dumps(
        {"cau": "Cắm sim là có wifi", "tu_khoa": ["cắm sim"]}), encoding="utf-8")
    (tmp_path / "01-BO-CANH-QUAY-1-BUOI.md").write_text("# BỘ CẢNH", encoding="utf-8")
    d = kho.doc_du_lieu_du_an(tmp_path)
    assert d["ten"] == "Router 4G" and d["gia"] == "199.000₫" and d["shop"] == "Homewise"
    assert d["anh_bia_url"] == "https://x/1.jpg"
    assert d["usp"]["cau"] == "Cắm sim là có wifi"
    assert d["file01"].name == "01-BO-CANH-QUAY-1-BUOI.md"


def test_doc_du_lieu_echotik(tmp_path):
    (tmp_path / "du_lieu_tho").mkdir()
    (tmp_path / "du_lieu_tho" / "san_pham.json").write_text(json.dumps({
        "product_id": UID, "product_name": "Router EchoTik", "real_price": "589.289₫",
        "seller": {"seller_name": "Homewise"}, "images": ["https://e/1.jpg"]}), encoding="utf-8")
    d = kho.doc_du_lieu_du_an(tmp_path)
    assert d["ten"] == "Router EchoTik" and d["gia"] == "589.289₫" and d["shop"] == "Homewise"
    assert d["anh_bia_url"] == "https://e/1.jpg"


def test_them_va_trung(tmp_path):
    data = tmp_path / "data"
    info, moi = kho.them_link(data, f"https://shop.tiktok.com/vn/pdp/{UID}?a=1", boi="Nhân")
    assert moi and info["uid"] == UID and info["them_boi"] == "Nhân"
    assert (data / UID / "info.json").exists()
    info2, moi2 = kho.them_link(data, UID, boi="Khác")
    assert not moi2 and info2["them_boi"] == "Nhân"


def test_them_link_rut_gon_tao_id_tam(tmp_path):
    data = tmp_path / "data"
    info, moi = kho.them_link(data, "https://vt.tiktok.com/ZSabc/", boi="Nhân")
    assert moi and info["uid"] is None and info["id"].startswith("tam-")
    _, moi2 = kho.them_link(data, "https://vt.tiktok.com/ZSabc/", boi="Nhân")
    assert not moi2


def test_doi_id_tam_sang_uid(tmp_path):
    data = tmp_path / "data"
    info, _ = kho.them_link(data, "https://vt.tiktok.com/ZSabc/", boi="Nhân")
    moi = kho.doi_sang_uid(data, info["id"], UID)
    assert moi["id"] == UID and moi["uid"] == UID
    assert not (data / info["id"]).exists() and (data / UID / "info.json").exists()


def test_tao_index(tmp_path):
    data = tmp_path / "data"
    kho.them_link(data, UID, boi="A")
    p = data / UID / "info.json"
    i = json.loads(p.read_text(encoding="utf-8"))
    i["da_phan_tich"] = True
    p.write_text(json.dumps(i), encoding="utf-8")
    (data / UID / "captions.txt").write_text("a\nb\n", encoding="utf-8")
    idx = kho.tao_index(data)
    assert idx["san_pham"][0]["id"] == UID
    assert idx["san_pham"][0]["trang_thai"] == "da_phan_tich"
    assert idx["san_pham"][0]["so_caption"] == 2
    assert idx["san_pham"][0]["da_quay_oneshot"]["xong"] is False
    assert idx["san_pham"][0]["da_quay_review"]["xong"] is False
