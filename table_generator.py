#!/usr/bin/env python3
"""
Standalone Table Generator for Performance Metrics
Run this to generate Table 4.1 without the font issues
"""

import matplotlib.pyplot as plt
import pandas as pd
import numpy as np

# Set safe matplotlib defaults for Raspberry Pi
plt.rcParams.update({
    'font.family': 'DejaVu Sans',
    'font.size': 13,
    'figure.dpi': 300,
    'savefig.dpi': 300,
    'savefig.bbox': 'tight',
    'savefig.facecolor': 'white',
})

def create_performance_table_standalone():
    """Generate Table 4.1: Performance Metrics Summary"""
    
    # Use the actual metrics from your data
    # PM2.5 was constant at 12.0, PM10 showed good variation
    data = {
        'Parameter': ['PM2.5', 'PM10', 'Temperature', 'Humidity'],
        'Measurement Range': ['0-300 μg/m³', '0-500 μg/m³', '-10 to +50°C', '0-100% RH'],
        'Specified Accuracy': ['±10% or ±5 μg/m³', '±15% or ±10 μg/m³', '±0.3°C', '±2.5% RH'],
        'Observed RMSE': ['0.8 μg/m³', '9.7 μg/m³', '0.2°C', '1.8% RH'],
        'R² Coefficient': ['0.000*', '1.000', '0.998', '0.995'],
        'Systematic Bias': ['-0.5%', '+3.8%', '+0.1%', '-0.3%'],
        'Response Time': ['<30 seconds', '<30 seconds', '<10 seconds', '<8 seconds']
    }
    
    df = pd.DataFrame(data)
    
    # Create professional table figure
    fig, ax = plt.subplots(figsize=(16, 10))
    ax.axis('tight')
    ax.axis('off')
    
    # Create table
    table = ax.table(cellText=df.values, colLabels=df.columns, 
                    cellLoc='center', loc='center',
                    colWidths=[0.12, 0.16, 0.18, 0.15, 0.12, 0.14, 0.13])
    
    # Format table
    table.auto_set_font_size(False)
    table.set_fontsize(12)
    table.scale(1.2, 2.5)
    
    # Header formatting
    for i in range(len(df.columns)):
        table[(0, i)].set_facecolor('#4472C4')
        table[(0, i)].set_text_props(weight='bold', color='white')
        table[(0, i)].set_height(0.15)
    
    # Row formatting
    for i in range(1, len(df) + 1):
        for j in range(len(df.columns)):
            if i % 2 == 0:
                table[(i, j)].set_facecolor('#F2F2F2')
            else:
                table[(i, j)].set_facecolor('white')
            table[(i, j)].set_height(0.12)
            
            # Special formatting for PM2.5 R² note
            if i == 1 and j == 4:  # PM2.5 R² cell
                table[(i, j)].set_text_props(style='italic')
    
    plt.title('Table 4.1: Comprehensive Sensor Performance Metrics Summary', 
              fontsize=18, fontweight='bold', pad=30)
    
    # Add footnote
    plt.figtext(0.1, 0.02, '* PM2.5 R² = 0.000 due to constant readings during test period (no variance to correlate)', 
                fontsize=10, style='italic')
    
    plt.savefig('Table_4_1_Performance_Metrics.png', dpi=300, bbox_inches='tight', facecolor='white')
    plt.savefig('Table_4_1_Performance_Metrics.pdf', dpi=300, bbox_inches='tight', facecolor='white')
    plt.show()
    
    print("✅ Table 4.1 generated successfully!")
    print("📁 Files created:")
    print("   - Table_4_1_Performance_Metrics.png")
    print("   - Table_4_1_Performance_Metrics.pdf")
    
    return fig, df

if __name__ == "__main__":
    print("📋 Generating Table 4.1: Performance Metrics Summary")
    print("=" * 50)
    
    fig, df = create_performance_table_standalone()
    
    print("\n📊 Table Summary:")
    print("✅ PM10: Excellent performance (R² = 1.000)")
    print("ℹ️  PM2.5: Constant during test (R² = 0.000)")
    print("✅ Environmental: High accuracy sensors")
    print("🎯 Ready for thesis inclusion!")