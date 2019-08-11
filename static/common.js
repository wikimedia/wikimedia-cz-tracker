window.showMessage = function ( message, alertType = 'alert-warning' ) {
	const errorContainer = document.querySelector( '.error-container' );
	const dismiss = document.createElement( 'a' );
	dismiss.classList.add( 'close' );
	dismiss.setAttribute( 'data-dismiss', 'alert' );
	dismiss.setAttribute( 'aria-label', 'close' );
	dismiss.textContent = '×';

	const errorMessage = document.createElement( 'div' );
	errorMessage.classList.add( 'alert', alertType, 'alert-dismissable' );
	errorMessage.textContent = message;
	errorMessage.appendChild( dismiss );
	errorContainer.appendChild( errorMessage );
};
