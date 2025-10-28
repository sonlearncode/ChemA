from chempy import balance_stoichiometry

def balance_equation(equation: str) -> str:
    """
    Input: "Fe + O2 -> Fe2O3"
    """
    try:
        left, right = equation.split("->")
        reactants = {x.strip(): 1 for x in left.split("+")}
        products  = {x.strip(): 1 for x in right.split("+")}
        reac, prod = balance_stoichiometry(reactants, products)
        l = " + ".join([f"{v} {k}" for k, v in reac.items()])
        r = " + ".join([f"{v} {k}" for k, v in prod.items()])
        return f"Cân bằng: {l} -> {r}"
    except Exception:
        return "Chưa cân bằng được, hãy kiểm tra công thức hoặc nhập dạng 'A + B -> C + D'."

def hint_stoichiometry():
    return (
        "Gợi ý nhanh:\n"
        "- n = m / M (mol = khối lượng / khối lượng mol)\n"
        "- V = n * 24.79 (L ở ĐKTC)\n"
        "- C_M = n / V (mol/L)"
    )
