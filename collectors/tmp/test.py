from collections import Counter

def main():
    # 標準入力からコードのリストを取得
    print("コードをスペース区切りで入力してください:")
    input_data = input().strip()
    
    # 入力をスペースで分割してリスト化
    codes = input_data.split()
    
    # 整数に変換可能なものを変換（文字列はそのままカウント可能）
    codes = [int(code) if code.isdigit() else code for code in codes]
    
    # コードの出現回数をカウント
    code_counts = Counter(codes)
    
    # 結果をソートして表示
    sorted_counts = sorted(code_counts.items(), key=lambda x: x[1], reverse=True)
    
    print("\n各コードの出現回数:")
    for code, count in sorted_counts:
        print(f"{code}: {count}回")

if __name__ == "__main__":
    main()

