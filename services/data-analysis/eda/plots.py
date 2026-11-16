"""Required correlation matrix; other required time plots live in eda.patterns."""
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import seaborn as sns

from eda.localization import FEATURE_LABELS


def generate_plots(frame, stations, tables, cadence, output):
    output.mkdir(parents=True, exist_ok=True)
    sns.set_theme(style='whitegrid', palette=['#167c70', '#b98a46', '#6989aa'])
    plt.rcParams.update({'font.family': 'DejaVu Sans', 'axes.titleweight': 'normal'})
    fig, ax = plt.subplots(figsize=(8, 7))
    if not stations or frame.empty:
        name, title = 'no_data.png', 'Khám phá dữ liệu: chưa có dữ liệu'
        ax.axis('off')
        ax.text(.5, .5, 'Chưa có quan sát được công bố trong khoảng đã chọn', ha='center')
    else:
        name = 'correlation_all.png'
        title = 'Tương quan Pearson · Mô tả mẫu gộp, không chứng minh nhân quả'
        matrix = tables['correlations']['ALL']['correlation'].rename(
            index=FEATURE_LABELS, columns=FEATURE_LABELS)
        if matrix.notna().any().any():
            sns.heatmap(matrix, mask=matrix.isna(), annot=True, fmt='.2f',
                cmap='vlag', vmin=-1, vmax=1, center=0, ax=ax)
        else:
            ax.axis('off')
            ax.text(.5, .5, 'Chưa đủ cặp quan sát hoặc đặc trưng không thay đổi',
                ha='center', transform=ax.transAxes)
    fig.suptitle(title, fontsize=14, color='#123b3a')
    fig.tight_layout(rect=(0, 0, 1, .96))
    fig.savefig(output / name, dpi=160, bbox_inches='tight')
    plt.close(fig)
    return [{'file': f'figures/{name}', 'title': title}]
