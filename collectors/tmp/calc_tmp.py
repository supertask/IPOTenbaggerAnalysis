def filter_numbers_in_range(lower_bound, upper_bound):
    import sys
    input_numbers = sys.stdin.read().strip().split()
    numbers = [int(num) for num in input_numbers]
    filtered_numbers = [num for num in numbers if lower_bound <= num <= upper_bound]
    return filtered_numbers

if __name__ == "__main__":
    # 範囲の定義
    lower_bound = 6098
    upper_bound = 7071
    
    # 結果のフィルタリングと表示
    result = filter_numbers_in_range(lower_bound, upper_bound)
    for num in result:
        print(num)

