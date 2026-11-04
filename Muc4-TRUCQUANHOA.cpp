#include <iostream>
#include <iomanip>
#include <string>
#include <vector>
using namespace std;
struct Segment{
    string name;
    int base;
    int limit;
    bool canRead;
    bool canWrite;
    bool canExecute;
};
void hienThiQuyen(const Segment& s){
    cout << "Read: " << (s.canRead ? "Co" : "Khong") << " | ";
    cout << "Write: " << (s.canWrite ? "Co" : "Khong") << " | ";
    cout << "Execute: " << (s.canExecute ? "Co" : "Khong") << '\n';
}
void hienThiBang(const vector<Segment>& segments){
    cout << "\n========== BANG PHAN DOAN ==========\n";
    cout << left << setw(10) << "STT" << setw(12) << "Ten" << setw(10) << "Base" << setw(10) << "Limit" << '\n';
    for (int i = 0; i < (int)segments.size(); i++){
        cout << left << setw(10) << i << setw(12) << segments[i].name << setw(10) << segments[i].base << setw(10) << segments[i].limit << '\n';
    }
}
void veMotSegment(const Segment& s, int index, int selectedSegment, int offset){
    const int maxWidth = 40;
    int width = s.limit / 10;
    if (width < 1) width = 1;
    if (width > maxWidth) width = maxWidth;
    cout << left << setw(8) << s.name << " ";
    for (int i = 0; i < width; i++) cout << '#';
    cout << "[" << s.base << " - " << s.base + s.limit - 1 << "]";
    if (index == selectedSegment && offset >= 0 && offset < s.limit){
        int markerPosition = offset * width / s.limit;
        cout << "\n         ";
        for (int i = 0; i < markerPosition; i++) cout << ' ';
        cout << "^\n         Dia chi dich nam tai offset " << offset;
    }
    cout << '\n';
}
void trucQuanHoaBoNho(const vector<Segment>& segments, int selectedSegment, int offset){
    cout << "\n========== SO DO BO NHO ==========\n";
    cout << "Moi # dai dien cho mot phan dung luong segment.\n\n";
    for (int i = 0; i < (int)segments.size(); i++) veMotSegment(segments[i], i, selectedSegment, offset);
    cout << "==================================\n";
}
string tenThaoTac(int operation){
    if (operation == 1) return "DOC";
    if (operation == 2) return "GHI";
    return "THUC THI";
}
bool coQuyen(const Segment& s, int operation){
    if (operation == 1) return s.canRead;
    if (operation == 2) return s.canWrite;
    return s.canExecute;
}
void moPhong(const vector<Segment>& segments){
    int segmentIndex, offset, operation;
    hienThiBang(segments);
    cout << "\nNhap so thu tu segment: ";
    cin >> segmentIndex;
    if (segmentIndex < 0 || segmentIndex >= (int)segments.size()){
        cout << "Loi: Segment khong ton tai!\n";
        return;
    }
    cout << "Nhap offset: ";
    cin >> offset;
    cout << "Chon thao tac (1. Doc, 2. Ghi, 3. Thuc thi): ";
    cin >> operation;
    if (offset < 0 || operation < 1 || operation > 3){
        cout << "Loi: Du lieu nhap khong hop le!\n";
        return;
    }
    const Segment& s = segments[segmentIndex];
    cout << "\n========== MO PHONG TUNG BUOC ==========\n";
    cout << "Buoc 1: Nhan dia chi logic.\n";
    cout << "Segment = " << segmentIndex << ", Offset = " << offset << '\n';
    cout << "\nBuoc 2: Kiem tra segment.\n";
    cout << "Ten: " << s.name << ", Base = " << s.base << ", Limit = " << s.limit << '\n';
    cout << "\nBuoc 3: Kiem tra quyen " << tenThaoTac(operation) << ".\n";
    hienThiQuyen(s);
    if (!coQuyen(s, operation)){
        cout << "Ket qua: TU CHOI truy cap do khong du quyen.\n";
        trucQuanHoaBoNho(segments, segmentIndex, -1);
        return;
    }
    cout << "\nBuoc 4: Kiem tra offset < limit.\n";
    if (offset >= s.limit){
        cout << "Ket qua: LOI - Offset vuot gioi han segment.\n";
        trucQuanHoaBoNho(segments, segmentIndex, -1);
        return;
    }
    cout << "Hop le: " << offset << " < " << s.limit << '\n';
    int physicalAddress = s.base + offset;
    cout << "\nBuoc 5: Tinh dia chi vat ly.\n";
    cout << "Physical Address = Base + Offset\n";
    cout << "                  = " << s.base << " + " << offset << " = " << physicalAddress << '\n';
    cout << "\nKet qua: TRUY CAP THANH CONG!\n";
    trucQuanHoaBoNho(segments, segmentIndex, offset);
}
int main(){
    vector<Segment> segments;
    segments.push_back({"Code", 0, 200, true, false, true});
    segments.push_back({"Data", 200, 150, true, true, false});
    segments.push_back({"Heap", 350, 250, true, true, false});
    segments.push_back({"Stack", 600, 180, true, true, false});
    int choice;
    do {
        cout << "\n========================================\n";
        cout << "   UNG DUNG TRUC QUAN HOA BO NHO\n";
        cout << "       MON HE DIEU HANH - C++\n";
        cout << "========================================\n";
        cout << "1. Xem bang segment\n";
        cout << "2. Xem so do bo nho\n";
        cout << "3. Mo phong dich dia chi tung buoc\n";
        cout << "0. Thoat\n";
        cout << "Nhap lua chon: ";
        if (!(cin >> choice)){
            cout << "Du lieu khong hop le. Vui long chay lai.\n";
            break;
        }
        switch (choice){
            case 1:
                hienThiBang(segments);
                break;
            case 2:
                trucQuanHoaBoNho(segments, -1, -1);
                break;
            case 3:
                moPhong(segments);
                break;
            case 0:
                cout << "Da thoat chuong trinh.\n";
                break;
            default:
                cout << "Lua chon khong hop le!\n";
        }
    }
    while (choice != 0);
    return 0;
}