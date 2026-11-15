# Bot chi tiêu: một tin nhắn đi qua những đâu

Code không gửi mọi tin cho LLM. Các bước dùng luật (code) chạy trước, theo thứ tự trong `bot.respond (interface/chitieu)`. LLM (Gemini
gói miễn phí, OpenRouter dự phòng) chỉ được gọi ở các ô màu cam.

```mermaid
flowchart TD
    U([📱 Tin nhắn Telegram]) --> W[api/chitieu.py<br/>webhook]
    W --> P{Ảnh?}
    P -- có --> V[🤖 LLM đọc ảnh<br/>docanh.py]
    V --> VK{Loại ảnh}
    VK -- hóa đơn, chuyển khoản --> REC
    VK -- lệnh quỹ, mua vàng, bán cổ phiếu --> CARD
    P -- chữ --> R

    subgraph R [interface/chitieu/bot.respond: luật đi trước, theo thứ tự]
        R1{Nút dưới ô chat?<br/>🏠 💰 🎯 💬} -- có --> S[Mở màn hình]
        R1 -- không --> R2{Nhiều dòng,<br/>dòng nào cũng /lệnh?}
        R2 -- có --> CMD[Chạy từng lệnh]
        R2 -- không --> R3{/lệnh?}
        R3 -- có --> CMD
        R3 -- không --> R4{Bot đang hỏi dở?<br/>troly.on_reply}
        R4 -- có --> R4a{Code đọc được<br/>câu trả lời ngắn?}
        R4a -- được --> NEXT[Hỏi tiếp / thẻ / làm]
        R4a -- không --> L1[🤖 LLM hiểu lời sửa]
        L1 --> NEXT
        R4 -- không --> R5{mua/bán cổ phiếu<br/>đúng mẫu?}
        R5 -- có --> TR[Ghi giao dịch]
        R5 -- không --> R6{mua VMEEF 3tr…?}
        R6 -- có --> FO[Ghi lệnh quỹ]
        R6 -- không --> R7{hôm nay không tiêu…?}
        R7 -- có --> NS[Đánh dấu không tiêu]
        R7 -- không --> R8{Câu hỏi?}
        R8 -- hỏi về chi tiêu đã ghi --> Q[phantich.hoi]
        R8 -- hỏi việc khác,<br/>hoặc có chữ báo hiệu<br/>quỹ, nợ, vàng, chuyển… --> L2
        R8 -- khoản chi thường --> REC
    end

    Q --> L3[🤖 LLM đổi câu hỏi<br/>thành bộ lọc]
    L3 -. lỗi .-> QR[Luật đơn giản]
    L3 --> QA[Code tính số liệu, trả lời]
    QR --> QA

    L2[🤖 LLM hiểu câu thành việc<br/>troly.ask_ai → JSON] --> CK[Code soát lại:<br/>bỏ trường lạ, đối chiếu số tiền]
    L2 -. lỗi .-> UN[Hỏi lại bằng nút<br/>hoặc ghi như khoản chi]
    CK --> J{Loại việc}
    J -- chi thường --> REC
    J -- thiếu thông tin --> ASK[Hỏi từng trường<br/>có nút chọn nhanh]
    J -- xem / hỏi --> S
    J -- đủ thông tin --> CARD[Thẻ 'Mình hiểu là…'<br/>✅ / ✏️ / ❌]
    ASK --> CARD
    CARD -- bấm ✅ --> ACT[Code thực hiện:<br/>quỹ, vàng, nợ, tiết kiệm,<br/>chuyển tiền, đối chiếu…]

    REC[Ghi khoản chi/thu<br/>code đọc số tiền, ngày] --> G{Nhóm?}
    G -- từ khóa, đã học --> OK[✅ Đã ghi]
    G -- lạ --> L4[🤖 LLM đoán nhóm ✨]
    L4 -. lỗi .-> ASKG[Hỏi nhóm bằng nút]
    L4 --> OK

    classDef llm fill:#ffe0b2,stroke:#e65100,color:#000
    class V,L1,L2,L3,L4 llm
```

| Bước | Ai làm | Khi nào |
|---|---|---|
| Nút, /lệnh, câu trả lời ngắn, mua/bán đúng mẫu, «không tiêu» | Code | Mọi lúc, không cần LLM |
| Khoản chi thường («cà phê 35k») | Code đọc số tiền; LLM chỉ đoán nhóm khi gặp ghi chú lạ | Phần lớn tin nhắn |
| Câu hỏi về chi tiêu | LLM đổi câu hỏi thành bộ lọc, **code tính số** | Câu có dấu hỏi, «bao nhiêu», «nhiều nhất»… |
| Việc tài chính (quỹ, vàng, nợ, chuyển tiền…) | **LLM hiểu ý**, code soát lại, người dùng bấm ✅ | Câu có chữ báo hiệu hoặc không có số tiền |
| Ảnh | LLM đọc ảnh | Mọi ảnh |

Bấm nút không bao giờ gọi LLM. LLM không bao giờ tự ghi gì: việc nào LLM hiểu ra cũng phải qua thẻ ✅, trừ khoản chi
thường (ghi ngay, có nút ✏️ sửa nhóm, ❌ xóa).
