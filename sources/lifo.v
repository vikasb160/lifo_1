`timescale 1ns/1ns
module lifo #(
    parameter DEPTH = 12,
    parameter DATA_WIDTH = 8
)(
    input wire clk,
    input wire rst,
    input wire [DATA_WIDTH-1:0] data_wr,
    input wire wr_en,
    output reg lifo_full,
    output reg [DATA_WIDTH-1:0] data_rd,
    input wire rd_en,
    output wire lifo_empty
);

endmodule