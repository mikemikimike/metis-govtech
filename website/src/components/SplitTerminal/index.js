import Pane from '@site/src/components/Terminal/Pane';
import styles from '@site/src/components/Terminal/styles.module.css';

export default function SplitTerminal({panes}) {
  return (
    <figure className={styles.window}>
      {panes.map(({label, command}, index) => (
        <Pane key={index} label={label ?? `Terminal ${index + 1}`} command={command} />
      ))}
    </figure>
  );
}
