#include <iostream>
#include <vector>
#include <string>

int main() {
    const int columns = 3;

    std::vector<std::string> lines;

    for (std::string line; std::getline(std::cin, line); ) {
        lines.push_back(line);
    }

    int rows_per_column = (lines.size() + columns - 1) / columns; // integer division rounds up

    for (int row = 0; row < rows_per_column; ++row) {
        std::cout << lines[row];
        for (int col = 1; col < columns; ++col) {
            int i = rows_per_column * col + row;
            if (i == lines.size()) break;
            std::cout << "  " << lines[i];
        }
        std::cout << "\n";
    }
}
